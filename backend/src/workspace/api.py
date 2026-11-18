from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import secrets
import threading
import time
from collections import Counter, defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import update

from meetings.availability import MeetingScheduleConfig, generate_slots
from workspace.config import (
    Settings,
    ROOT,
    initial_businesses,
    validate_business,
    secret,
)
from workspace.database import Database, jobs
from workspace.engine import initialize, merge_lead, now_iso, respond
from workspace.schemas import (
    Login,
    SessionInput,
    ChatInput,
    BookInput,
    RequestInput,
    LeadPatch,
    ReplyInput,
    KnowledgeInput,
    SalesRequestPatch,
)
from workspace.security import new_session, get_session, revoke, check_password, digest
from workspace.consent import requests_optout, record_consent, is_suppressed
from workspace.reporting import capture_source, summarize
from workspace.http_limits import RequestBodyLimitMiddleware


def create_app(settings=None):
    settings = settings or Settings()
    db = Database(settings.database_url)
    initialize(db, settings, initial_businesses(settings))
    app = FastAPI(
        title="Systematic Sales Workspace",
        version="1.0.0",
        docs_url="/api/docs" if settings.mode == "demo" else None,
        redoc_url=None,
    )
    app.state.db, app.state.settings = db, settings
    app.add_middleware(RequestBodyLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-Workspace-Request"],
    )
    requests = defaultdict(deque)
    rate_lock = threading.Lock()

    @app.middleware("http")
    async def guard(request, call_next):
        path = request.url.path
        if path.startswith("/api/"):
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                origin = request.headers.get("origin")
                if origin and origin not in settings.origins:
                    return JSONResponse(
                        {"detail": "This origin is not allowed"}, status_code=403
                    )
                if request.headers.get("x-workspace-request") != "1":
                    return JSONResponse(
                        {"detail": "Missing request verification header"},
                        status_code=403,
                    )
            # Trust the actual peer; never trust a visitor-supplied X-Forwarded-For.
            identity = (
                request.client.host if request.client else "local",
                (
                    "login"
                    if "login" in path
                    else "public" if "/public/" in path else "admin"
                ),
            )
            limit = 15 if identity[1] == "login" else 120
            now = time.monotonic()
            with rate_lock:
                if len(requests) > 10000:
                    for key in list(requests):
                        if not requests[key] or now - requests[key][-1] > 60:
                            del requests[key]
                queue = requests[identity]
                while queue and queue[0] < now - 60:
                    queue.popleft()
                if len(queue) >= limit:
                    return JSONResponse(
                        {"detail": "Too many requests. Please wait a minute."},
                        status_code=429,
                        headers={"Retry-After": "60"},
                    )
                queue.append(now)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        return JSONResponse(
            {
                "detail": "The request could not be completed. Please retry or contact the team."
            },
            status_code=500,
        )

    def business(tenant):
        value = db.get(tenant, "business", tenant)
        if not value:
            raise HTTPException(404, "Business not found")
        return value

    def admin(request: Request):
        session = get_session(db, request.cookies.get("workspace_session"), "admin")
        if not session:
            raise HTTPException(401, "Sign in to your workspace")
        return session

    def visitor(request: Request):
        value = request.headers.get("authorization", "")
        session = get_session(
            db, value[7:] if value.startswith("Bearer ") else "", "visitor"
        )
        if not session:
            raise HTTPException(401, "Start a new conversation")
        return session

    def auth_response(tenant, subject):
        token = new_session(db, tenant, "admin", subject)
        result = JSONResponse({"business": tenant, "mode": settings.mode})
        result.set_cookie(
            "workspace_session",
            token,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="strict",
            max_age=28800,
            path="/",
        )
        return result

    def schedule(tenant):
        b = business(tenant)
        h = b["working_hours"]
        return MeetingScheduleConfig(
            timezone=b["timezone"],
            workday_start=h["start"],
            workday_end=h["end"],
            duration_minutes=h["duration"],
            buffer_minutes=h["buffer"],
        )

    def calendar_gateway(tenant):
        from integrations.google_calendar.gateway import GoogleCalendarGateway
        from integrations.google_calendar.config import GoogleCalendarConfig

        b = business(tenant)
        token_file = secret(settings, tenant, "GOOGLE_CALENDAR_TOKEN_FILE")
        calendar_id = secret(settings, tenant, "GOOGLE_CALENDAR_ID")
        if not b["integrations"].get("calendar") or not token_file or not calendar_id:
            raise HTTPException(
                503, "Calendar is not connected. Please request a callback instead."
            )
        token_path = Path(token_file)
        return GoogleCalendarGateway(
            GoogleCalendarConfig(
                enabled=True,
                calendar_id=calendar_id,
                timezone=b["timezone"],
                token_file=(
                    token_path if token_path.is_absolute() else ROOT / token_path
                ),
            ),
            schedule=schedule(tenant),
        )

    def enqueue_events(tenant, event, lead, key, conn):
        b = business(tenant)
        for kind in ("email", "sheets", "crm"):
            if kind == "email" or b["integrations"].get(kind):
                db.enqueue(
                    tenant,
                    kind,
                    f"{event}:{key}:{kind}",
                    {"event": event, "lead_id": lead["id"]},
                    conn=conn,
                )
        if (
            event in ("new_lead", "proposal_requested")
            and lead.get("consent_status") == "granted"
        ):
            db.enqueue(
                tenant,
                "followup",
                f'followup:{lead["id"]}',
                {"event": "followup", "lead_id": lead["id"]},
                delay=b.get("followup_hours", 24) * 3600,
                conn=conn,
            )

    def sync_lead(tenant, lead, conn):
        b = business(tenant)
        revision = uuid4().hex
        for kind in ("sheets", "crm"):
            if b["integrations"].get(kind):
                db.enqueue(
                    tenant,
                    kind,
                    f"lead_updated:{revision}:{kind}",
                    {"event": "lead_updated", "lead_id": lead["id"]},
                    conn=conn,
                )

    def contact_lead(session, data, action, conn=None):
        tenant, conv_id = session["tenant"], session["subject"]
        b = business(tenant)
        if data.service not in b["services"]:
            raise HTTPException(422, "Choose a service from the business catalog")
        conv = db.get(tenant, "conversation", conv_id, conn)
        previous = db.get(tenant, "lead", conv.get("lead_id") or "", conn)
        lead = merge_lead(
            previous,
            {
                "full_name": data.name,
                "email": data.email,
                "company_name": data.company,
                "required_services": [data.service],
                "business_goal": data.goal,
            },
            b,
            len(conv["messages"]) // 2 + 1,
            action,
        )
        lead.update(conversation_id=conv_id, source_page=conv["source_page"])
        lead["consent_status"] = (
            "granted"
            if data.consent
            else (
                previous.get("consent_status", "not_requested")
                if previous
                else "not_requested"
            )
        )
        if conv.get("opted_out") or is_suppressed(db, tenant, lead.get("email"), conn):
            lead["consent_status"] = "declined"
        conv["lead_id"] = lead["id"]
        return conv, lead

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": settings.mode, "version": "1.0.0"}

    @app.post("/api/auth/demo")
    def demo_login(data: Login):
        if settings.mode != "demo":
            raise HTTPException(404, "Not found")
        business(data.business)
        return auth_response(data.business, "Demo operator")

    @app.post("/api/auth/login")
    def login(data: Login):
        business(data.business)
        encoded = secret(settings, data.business, "ADMIN_PASSWORD_HASH")
        expected = secret(settings, data.business, "ADMIN_EMAIL")
        if (
            not encoded
            or not expected
            or not secrets.compare_digest(data.email.lower(), expected.lower())
            or not check_password(data.password, encoded)
        ):
            raise HTTPException(401, "Invalid workspace, email or password")
        return auth_response(data.business, expected)

    @app.post("/api/auth/logout")
    def logout(request: Request):
        revoke(db, request.cookies.get("workspace_session"))
        result = JSONResponse({"ok": True})
        result.delete_cookie("workspace_session", path="/")
        return result

    @app.get("/api/admin/workspace")
    def workspace(session=Depends(admin)):
        tenant = session["tenant"]
        leads = db.list(tenant, "lead")
        conversations = db.list(tenant, "conversation")
        meetings = db.list(tenant, "meeting")
        documents = db.list(tenant, "knowledge")
        counts = Counter(l["stage"] for l in leads)
        days = [
            (datetime.now(timezone.utc) - timedelta(days=i)).date().isoformat()
            for i in range(13, -1, -1)
        ]
        return {
            "business": business(tenant),
            "mode": settings.mode,
            "operator": session["subject"],
            "period_counts": {
                str(days): summarize(conversations, leads, meetings, [], days)["counts"]
                for days in (7, 14)
            },
            "leads": leads,
            "conversations": [
                {**c, "messages": c["messages"][-2:]} for c in conversations[:200]
            ],
            "meetings": meetings,
            "requests": db.list(tenant, "request"),
            "booking_reviews": [
                {
                    "id": r["offer_id"],
                    "status": r["status"],
                    "created": r.get("created", 0),
                    "name": r.get("meeting", {}).get("name", "Visitor"),
                }
                for r in db.list(tenant, "reservation")
                if r["status"] in ("pending", "needs_review")
            ],
            "jobs": [
                {
                    k: v
                    for k, v in j.items()
                    if k not in ("payload", "lease_token", "dedupe")
                }
                for j in db.list_jobs(tenant)
            ],
            "knowledge": [{**d, "content": d["content"][:180]} for d in documents],
            "metrics": {
                "visitors": len(db.list(tenant, "visit")),
                "conversations": len(conversations),
                "leads": sum(l["stage"] != "anonymous" for l in leads),
                "hot": sum(l["lead_classification"] == "Hot" for l in leads),
                "qualified": sum(
                    l["stage"]
                    in (
                        "qualified",
                        "meeting_booked",
                        "meeting_attended",
                        "proposal_requested",
                        "proposal_sent",
                        "won",
                    )
                    for l in leads
                ),
                "won": counts["won"],
                "meetings": len(meetings),
            },
            "trend": [
                {
                    "date": day,
                    "leads": sum(l["created_at"][:10] == day for l in leads),
                    "conversations": sum(
                        c["created_at"][:10] == day for c in conversations
                    ),
                }
                for day in days
            ],
            "integrations": integration_status(tenant),
        }

    def integration_status(tenant):
        b = business(tenant)
        required = {
            "ai": ["GEMINI_API_KEY"],
            "calendar": ["GOOGLE_CALENDAR_ID", "GOOGLE_CALENDAR_TOKEN_FILE"],
            "email": ["SMTP_HOST", "SMTP_FROM"],
            "sheets": ["GOOGLE_SHEET_ID", "GOOGLE_SHEETS_TOKEN_FILE"],
            "crm": ["CRM_WEBHOOK_URL", "CRM_API_KEY"],
        }
        return [
            {
                "id": name,
                "enabled": True if name == "ai" else b["integrations"].get(name, False),
                "configured": all(secret(settings, tenant, key) for key in keys),
                "status": (
                    "demo"
                    if settings.mode == "demo"
                    else (
                        "configured"
                        if all(secret(settings, tenant, key) for key in keys)
                        else "setup_required"
                    )
                ),
                "required": keys,
            }
            for name, keys in required.items()
        ]

    @app.get("/api/admin/insights")
    def insights(days: int = 14, session=Depends(admin)):
        if days not in (7, 14, 30, 90):
            raise HTTPException(422, "Choose 7, 14, 30 or 90 days")
        tenant = session["tenant"]
        return summarize(
            db.list(tenant, "conversation"),
            db.list(tenant, "lead"),
            db.list(tenant, "meeting"),
            db.list(tenant, "request"),
            days,
        )

    @app.get("/api/admin/leads/{lead_id}/related")
    def related_contacts(lead_id: str, session=Depends(admin)):
        tenant = session["tenant"]
        lead = db.get(tenant, "lead", lead_id)
        if not lead:
            raise HTTPException(404, "Lead not found")
        email = (lead.get("email") or "").strip().casefold()
        matches = [
            l
            for l in db.list(tenant, "lead")
            if email
            and l["id"] != lead_id
            and (l.get("email") or "").strip().casefold() == email
        ]
        return {
            "matches": [
                {
                    k: l.get(k)
                    for k in (
                        "id",
                        "full_name",
                        "company_name",
                        "created_at",
                        "stage",
                        "required_services",
                        "business_goal",
                    )
                }
                for l in matches
            ],
            "basis": "same_email_unverified",
        }

    @app.patch("/api/admin/requests/{request_id}")
    def update_sales_request(
        request_id: str, data: SalesRequestPatch, session=Depends(admin)
    ):
        tenant = session["tenant"]
        with db.transaction(tenant) as c:
            item = db.get(tenant, "request", request_id, c)
            if not item:
                raise HTTPException(404, "Sales request not found")
            if item.get("version", 0) != data.expected_version:
                raise HTTPException(
                    409, "This request changed. Refresh the workspace before saving."
                )
            if data.status == "in_progress" and not data.owner:
                raise HTTPException(422, "Assign an owner before starting work")
            if (
                data.status == "completed"
                and item["status"] != "completed"
                and not data.note
            ):
                raise HTTPException(
                    422, "Add an outcome note before completing the request"
                )
            stamp = now_iso()
            item.update(
                status=data.status,
                owner=data.owner,
                due_at=data.due_at.isoformat() if data.due_at else None,
                version=data.expected_version + 1,
                updated_at=stamp,
            )
            item["completed_at"] = (
                (item.get("completed_at") or stamp)
                if data.status == "completed"
                else None
            )
            item.setdefault("history", []).append(
                {
                    "status": data.status,
                    "owner": data.owner,
                    "due_at": item["due_at"],
                    "note": data.note,
                    "actor": session["subject"],
                    "created_at": stamp,
                }
            )
            db.put(tenant, "request", request_id, item, c)
        return item

    @app.get("/api/admin/leads/export")
    def export(session=Depends(admin)):
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(
            ["Name", "Company", "Email", "Service", "Score", "Stage", "Owner"]
        )
        for l in db.list(session["tenant"], "lead"):
            fields = [
                l.get("full_name", ""),
                l.get("company_name", ""),
                l.get("email", ""),
                ", ".join(l.get("required_services", [])),
                l.get("lead_score", 0),
                l["stage"],
                l.get("assigned_sales_rep", ""),
            ]
            writer.writerow(
                [
                    "'" + str(v) if str(v).startswith(("=", "+", "-", "@")) else v
                    for v in fields
                ]
            )
        return Response(
            stream.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="leads.csv"'},
        )

    @app.patch("/api/admin/leads/{lead_id}")
    def patch_lead(lead_id: str, data: LeadPatch, session=Depends(admin)):
        tenant = session["tenant"]
        with db.transaction(tenant) as c:
            lead = db.get(tenant, "lead", lead_id, c)
            if not lead:
                raise HTTPException(404, "Lead not found")
            changes = data.model_dump(exclude_none=True)
            note = changes.pop("note", None)
            if (
                changes.get("stage") == "lost"
                and not changes.get("lost_reason")
                and not lead.get("lost_reason")
            ):
                raise HTTPException(422, "A lost reason is required")
            if changes.get("due_at"):
                try:
                    datetime.fromisoformat(changes["due_at"])
                except ValueError:
                    raise HTTPException(422, "Invalid next-action date")
            lead.update(changes, updated_at=now_iso())
            if "consent_status" in changes:
                record_consent(
                    db,
                    tenant,
                    lead,
                    changes["consent_status"],
                    "operator:" + session["subject"],
                    c,
                    allow_resubscribe=True,
                )
            if note:
                lead.setdefault("notes", []).append(
                    {
                        "text": note,
                        "author": session["subject"],
                        "created_at": now_iso(),
                    }
                )
            db.put(tenant, "lead", lead_id, lead, c)
            # State changes must reach connected systems after initial capture too.
            revision = uuid4().hex
            b = business(tenant)
            for kind in ("sheets", "crm"):
                if b["integrations"].get(kind):
                    db.enqueue(
                        tenant,
                        kind,
                        f"lead_updated:{revision}:{kind}",
                        {"event": "lead_updated", "lead_id": lead_id},
                        conn=c,
                    )
            db.put(
                tenant,
                "lead_event",
                revision,
                {
                    "id": revision,
                    "lead_id": lead_id,
                    "changes": changes,
                    "actor": session["subject"],
                    "created_at": now_iso(),
                },
                c,
            )
        return lead

    @app.get("/api/admin/conversations/{conv_id}")
    def conversation(conv_id: str, session=Depends(admin)):
        conv = db.get(session["tenant"], "conversation", conv_id)
        if not conv:
            raise HTTPException(404, "Conversation not found")
        return conv

    @app.post("/api/admin/conversations/{conv_id}/takeover")
    def takeover(conv_id: str, session=Depends(admin)):
        with db.transaction(session["tenant"]) as c:
            conv = db.get(session["tenant"], "conversation", conv_id, c)
            if not conv:
                raise HTTPException(404, "Conversation not found")
            conv["status"] = "human" if conv["status"] != "human" else "active"
            conv["updated_at"] = now_iso()
            db.put(session["tenant"], "conversation", conv_id, conv, c)
        return conv

    @app.post("/api/admin/conversations/{conv_id}/reply")
    def human_reply(conv_id: str, data: ReplyInput, session=Depends(admin)):
        with db.transaction(session["tenant"]) as c:
            conv = db.get(session["tenant"], "conversation", conv_id, c)
            if not conv:
                raise HTTPException(404, "Conversation not found")
            if conv["status"] != "human":
                raise HTTPException(409, "Take over the conversation before replying")
            conv["messages"].append(
                {
                    "id": uuid4().hex,
                    "role": "assistant",
                    "author": "Sales team",
                    "content": data.message,
                    "created_at": now_iso(),
                }
            )
            conv["updated_at"] = now_iso()
            db.put(session["tenant"], "conversation", conv_id, conv, c)
        return conv

    @app.post("/api/admin/jobs/{job_id}/retry")
    def retry(job_id: str, session=Depends(admin)):
        with db.transaction() as c:
            result = c.execute(
                update(jobs)
                .where(
                    jobs.c.id == job_id,
                    jobs.c.tenant == session["tenant"],
                    jobs.c.status.in_(["failed", "blocked"]),
                )
                .values(status="pending", due=time.time(), attempts=0, error=None)
            )
            if not result.rowcount:
                raise HTTPException(409, "Only failed or blocked jobs can be retried")
        return {"ok": True}

    @app.post("/api/admin/jobs/demo-process")
    def demo_jobs(session=Depends(admin)):
        if settings.mode != "demo":
            raise HTTPException(404, "Not found")
        from workspace.worker import process_one

        count = 0
        while count < 30 and process_one(db, settings, session["tenant"]):
            count += 1
        return {"processed": count}

    @app.post("/api/admin/knowledge")
    def add_knowledge(data: KnowledgeInput, session=Depends(admin)):
        b = business(session["tenant"])
        if data.source_url:
            u = urlparse(data.source_url)
            if f"{u.scheme}://{u.netloc}" not in b["allowed_origins"]:
                raise HTTPException(
                    422, "Source URL must belong to an approved business website"
                )
        key = uuid4().hex
        doc = {**data.model_dump(), "id": key, "updated_at": now_iso()}
        db.put(session["tenant"], "knowledge", key, doc)
        return doc

    @app.delete("/api/admin/knowledge/{doc_id}")
    def delete_knowledge(doc_id: str, session=Depends(admin)):
        if not db.get(session["tenant"], "knowledge", doc_id):
            raise HTTPException(404, "Document not found")
        db.remove(session["tenant"], "knowledge", doc_id)
        return {"ok": True}

    @app.patch("/api/admin/settings")
    async def patch_settings(request: Request, session=Depends(admin)):
        changes = await request.json()
        allowed = {
            "name",
            "short_name",
            "welcome",
            "tagline",
            "accent",
            "services",
            "timezone",
            "qualification",
            "notification_email",
            "followup_hours",
            "integrations",
            "allowed_origins",
            "navigation",
            "working_hours",
        }
        if not isinstance(changes, dict) or set(changes) - allowed:
            raise HTTPException(422, "Unsupported settings fields")
        tenant = session["tenant"]
        with db.transaction(tenant) as c:
            b = {**db.get(tenant, "business", tenant, c), **changes}
            try:
                b = validate_business(b)
            except (ValueError, TypeError, KeyError) as exc:
                raise HTTPException(422, str(exc))
            db.put(tenant, "business", tenant, b, c)
        return b

    @app.get("/api/public/config/{tenant}")
    def public_config(tenant: str, request: Request, response: Response):
        b = business(tenant)
        origin = request.headers.get("origin")
        if origin in b["allowed_origins"]:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
        return {
            **{
                k: b.get(k)
                for k in [
                    "id",
                    "name",
                    "short_name",
                    "tagline",
                    "accent",
                    "welcome",
                    "website",
                    "services",
                    "timezone",
                    "navigation",
                    "allowed_origins",
                ]
            },
            "mode": settings.mode,
            "meeting_duration": b["working_hours"]["duration"],
        }

    @app.post("/api/public/session")
    def start_session(data: SessionInput):
        b = business(data.business)
        key = uuid4().hex
        source, attribution = capture_source(
            data.source_page, b["website"], [*b["allowed_origins"], *settings.origins]
        )
        conv = {
            "id": key,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "status": "active",
            "lead_id": None,
            "source_page": source,
            "attribution": attribution,
            "messages": [],
        }
        with db.transaction() as c:
            db.put(b["id"], "conversation", key, conv, c)
            db.put(
                b["id"],
                "visit",
                key,
                {
                    "id": key,
                    "created_at": now_iso(),
                    "source_page": source,
                    "attribution": attribution,
                },
                c,
            )
        return {"token": new_session(db, b["id"], "visitor", key), "conversation": conv}

    @app.get("/api/public/conversation")
    def visitor_history(session=Depends(visitor)):
        return db.get(session["tenant"], "conversation", session["subject"])

    @app.post("/api/public/chat")
    def chat(data: ChatInput, session=Depends(visitor)):
        tenant, conv_id = session["tenant"], session["subject"]
        key = conv_id + ":" + data.request_id
        previous = db.get(tenant, "chat_result", key)
        if previous:
            original = next(
                (
                    m["content"]
                    for m in previous["conversation"]["messages"]
                    if m["id"] == data.request_id and m["role"] == "user"
                ),
                None,
            )
            if original != data.message:
                raise HTTPException(
                    409,
                    "This request ID belongs to another message. Send the edited message with a new ID.",
                )
            return previous
        lock = {"created": time.time(), "token": uuid4().hex}
        if not db.create_once(tenant, "chat_lock", conv_id, lock):
            with db.transaction(tenant) as c:
                old = db.get(tenant, "chat_lock", conv_id, c)
                if old and old["created"] < time.time() - 300:
                    db.remove(tenant, "chat_lock", conv_id, c)
            raise HTTPException(
                409, "A reply is already in progress. Please retry shortly."
            )
        try:
            conv = db.get(tenant, "conversation", conv_id)
            b = business(tenant)
            optout = requests_optout(data.message)
            if len(conv["messages"]) >= 200 and not optout:
                raise HTTPException(422, "Please start a new conversation")
            quiet = {
                "answer": "",
                "intent": "human",
                "action": "none",
                "sources": [],
                "lead_updates": {},
            }
            if optout:
                result = {
                    **quiet,
                    "answer": "Your request to stop email follow-ups has been recorded.",
                }
            elif conv["status"] == "human":
                result = quiet
            else:
                result = respond(db, settings, b, data.message, conv["messages"])
            with db.transaction(tenant) as c:
                # A timeout cannot let the old owner overwrite a newer reply.
                if db.get(tenant, "chat_lock", conv_id, c) != lock:
                    raise HTTPException(
                        409, "This reply expired. Please retry with the same message."
                    )
                conv = db.get(tenant, "conversation", conv_id, c)
                if conv["status"] == "human" and not optout:
                    result = quiet
                stamp = now_iso()
                conv["messages"].append(
                    {
                        "id": data.request_id,
                        "role": "user",
                        "content": data.message,
                        "created_at": stamp,
                    }
                )
                if result["answer"]:
                    conv["messages"].append(
                        {
                            "id": uuid4().hex,
                            "role": "assistant",
                            "content": result["answer"],
                            "action": result["action"],
                            "sources": result["sources"],
                            "grounding_status": result.get("grounding_status"),
                            "created_at": stamp,
                        }
                    )
                conv["updated_at"] = stamp
                if optout:
                    conv["opted_out"] = True
                meaningful = (
                    result["intent"]
                    in (
                        "service_discovery",
                        "service_recommendation",
                        "pricing",
                        "booking_interest",
                        "proposal_interest",
                    )
                    or result["lead_updates"].get("email")
                    or result["lead_updates"].get("phone")
                )
                if meaningful or conv.get("lead_id"):
                    previous_lead = db.get(tenant, "lead", conv.get("lead_id") or "", c)
                    lead = merge_lead(
                        previous_lead,
                        result["lead_updates"],
                        b,
                        sum(m["role"] == "user" for m in conv["messages"]),
                        result["action"],
                    )
                    lead.update(
                        conversation_id=conv_id, source_page=conv["source_page"]
                    )
                    if (
                        optout
                        or conv.get("opted_out")
                        or is_suppressed(db, tenant, lead.get("email"), c)
                    ):
                        record_consent(db, tenant, lead, "declined", "visitor_chat", c)
                    conv["lead_id"] = lead["id"]
                    db.put(tenant, "lead", lead["id"], lead, c)
                    if lead.get("email") and not (previous_lead or {}).get("email"):
                        enqueue_events(tenant, "new_lead", lead, lead["id"], c)
                    elif previous_lead:
                        sync_lead(tenant, lead, c)
                db.put(tenant, "conversation", conv_id, conv, c)
                output = {
                    "conversation": conv,
                    "action": result["action"],
                    "mode": settings.mode,
                }
                db.put(tenant, "chat_result", key, output, c)
            return output
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                503,
                "The assistant is temporarily unavailable. Please retry or request a human conversation.",
            )
        finally:
            with db.transaction(tenant) as c:
                if db.get(tenant, "chat_lock", conv_id, c) == lock:
                    db.remove(tenant, "chat_lock", conv_id, c)

    @app.get("/api/public/availability")
    def availability(day: date, session=Depends(visitor)):
        tenant = session["tenant"]
        b, config = business(tenant), schedule(tenant)
        current = datetime.now(ZoneInfo(b["timezone"]))
        if not current.date() <= day <= current.date() + timedelta(days=60):
            raise HTTPException(422, "Choose a date within the next 60 days")
        busy = []
        for meeting in db.list(tenant, "meeting"):
            if meeting["status"] not in ("cancelled", "failed"):
                busy.append(
                    (
                        datetime.fromisoformat(meeting["start_at"]),
                        datetime.fromisoformat(meeting["end_at"]),
                    )
                )
        for reservation in db.list(tenant, "reservation"):
            if reservation["status"] in ("pending", "needs_review"):
                held = db.get(tenant, "offer", reservation["offer_id"])
                if held:
                    busy.append(
                        (
                            datetime.fromisoformat(held["start_at"]),
                            datetime.fromisoformat(held["end_at"]),
                        )
                    )
        if settings.mode == "live":
            try:
                gateway = calendar_gateway(tenant)
                start = datetime.combine(
                    day, datetime.min.time(), ZoneInfo(b["timezone"])
                )
                busy += gateway.get_busy_intervals(
                    start, start + timedelta(days=1), b["timezone"]
                )
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(
                    503, "Calendar availability could not be verified. Try again later."
                )
        slots = generate_slots(day, busy, config)
        offered = []
        for slot in slots:
            if slot.start_at <= current + timedelta(minutes=30):
                continue
            key = uuid4().hex
            offer = {
                "id": key,
                "conversation_id": session["subject"],
                "start_at": slot.start_at.isoformat(),
                "end_at": slot.end_at.isoformat(),
                "timezone": slot.timezone,
                "expires": time.time() + 600,
            }
            db.put(tenant, "offer", key, offer)
            offered.append(offer)
        return {"slots": offered, "mode": settings.mode}

    @app.post("/api/public/book")
    def book(data: BookInput, session=Depends(visitor)):
        tenant, conv_id = session["tenant"], session["subject"]
        with db.transaction(tenant) as c:
            offer = db.get(tenant, "offer", data.offer_id, c)
            if not offer or offer["conversation_id"] != conv_id:
                raise HTTPException(404, "Booking offer not found")
            existing = db.get(tenant, "meeting", data.offer_id, c)
            if existing:
                return existing
            if offer["expires"] < time.time() or datetime.fromisoformat(
                offer["start_at"]
            ) <= datetime.now(timezone.utc):
                raise HTTPException(
                    409, "This offer has expired. Please choose a new time."
                )
            start, end = datetime.fromisoformat(
                offer["start_at"]
            ), datetime.fromisoformat(offer["end_at"])
            reserve = hashlib.sha256(offer["start_at"].encode()).hexdigest()
            held = db.get(tenant, "reservation", reserve, c)
            if held:
                raise HTTPException(
                    409,
                    "This time is reserved or being confirmed. Choose another slot or ask the team to check it.",
                )
            busy = [
                (m["start_at"], m["end_at"])
                for m in db.list(tenant, "meeting", c)
                if m["status"] not in ("cancelled", "failed")
            ]
            for r in db.list(tenant, "reservation", c):
                if r["status"] in ("pending", "needs_review"):
                    slot = db.get(tenant, "offer", r["offer_id"], c)
                    if slot:
                        busy.append((slot["start_at"], slot["end_at"]))
            buffer = timedelta(minutes=schedule(tenant).buffer_minutes)
            if any(
                start < datetime.fromisoformat(finish) + buffer
                and end > datetime.fromisoformat(begin) - buffer
                for begin, finish in busy
            ):
                raise HTTPException(
                    409, "This time is no longer available. Choose another slot."
                )
            conv, lead = contact_lead(session, data, "book_meeting", c)
            if data.consent:
                record_consent(db, tenant, lead, "granted", "visitor_booking", c)
            meeting = {
                "id": data.offer_id,
                "lead_id": lead["id"],
                "conversation_id": conv_id,
                "name": data.name,
                "email": data.email,
                "service": data.service,
                "start_at": offer["start_at"],
                "end_at": offer["end_at"],
                "timezone": offer["timezone"],
                "status": "simulated" if settings.mode == "demo" else "booked",
                "created_at": now_iso(),
            }
            reservation = {
                "offer_id": data.offer_id,
                "conversation_id": conv_id,
                "status": "pending",
                "created": time.time(),
                "meeting": meeting,
                "lead": lead,
                "conversation": conv,
            }
            db.put(tenant, "lead", lead["id"], lead, c)
            db.put(tenant, "conversation", conv_id, conv, c)
            db.put(tenant, "reservation", reserve, reservation, c)
        insertion_started = False
        if settings.mode == "live":
            try:
                gateway = calendar_gateway(tenant)
                event_id = hashlib.sha256((tenant + data.offer_id).encode()).hexdigest()
                if not gateway.slot_is_free(
                    start - buffer, end + buffer, offer["timezone"]
                ):
                    raise HTTPException(
                        409, "This time is no longer available. Choose another slot."
                    )
                request = gateway.service.events().insert(
                    calendarId=gateway.config.calendar_id,
                    body={
                        "id": event_id,
                        "summary": business(tenant)["name"] + " - Consultation",
                        "start": {
                            "dateTime": offer["start_at"],
                            "timeZone": offer["timezone"],
                        },
                        "end": {
                            "dateTime": offer["end_at"],
                            "timeZone": offer["timezone"],
                        },
                        "attendees": [{"email": data.email}],
                    },
                    sendUpdates="all",
                )
                insertion_started = True
                created = request.execute()
                meeting["external_event_id"] = created["id"]
                meeting["external_event_url"] = created.get("htmlLink")
            except Exception as exc:
                if insertion_started:
                    db.put(
                        tenant,
                        "reservation",
                        reserve,
                        {**reservation, "status": "needs_review"},
                    )
                    raise HTTPException(
                        503,
                        "Booking could not be confirmed. The team must verify this time before another attempt.",
                    ) from exc
                db.remove(tenant, "reservation", reserve)
                if isinstance(exc, HTTPException):
                    raise
                raise HTTPException(
                    503,
                    "Calendar availability could not be verified. No event was requested; please try again later.",
                ) from exc
        with db.transaction(tenant) as c:
            # Read current state after the external call; never restore old snapshots.
            conv = db.get(tenant, "conversation", conv_id, c)
            lead = db.get(tenant, "lead", meeting["lead_id"], c)
            lead.update(
                stage="meeting_booked", meeting_requested=True, updated_at=now_iso()
            )
            conv["messages"].append(
                {
                    "id": uuid4().hex,
                    "role": "assistant",
                    "content": (
                        "Demo appointment saved. No external calendar event was created."
                        if settings.mode == "demo"
                        else "Your consultation is booked."
                    ),
                    "created_at": now_iso(),
                }
            )
            conv["updated_at"] = now_iso()
            db.put(tenant, "meeting", meeting["id"], meeting, c)
            db.put(tenant, "lead", lead["id"], lead, c)
            db.put(tenant, "conversation", conv_id, conv, c)
            db.put(
                tenant,
                "reservation",
                reserve,
                {"offer_id": data.offer_id, "status": "completed"},
                c,
            )
            enqueue_events(tenant, "meeting_booked", lead, meeting["id"], c)
        return meeting

    @app.post("/api/admin/bookings/{offer_id}/reconcile")
    def reconcile(offer_id: str, session=Depends(admin)):
        tenant = session["tenant"]
        offer = db.get(tenant, "offer", offer_id)
        if not offer:
            raise HTTPException(404, "Booking offer not found")
        key = hashlib.sha256(offer["start_at"].encode()).hexdigest()
        reservation = db.get(tenant, "reservation", key)
        if (
            not reservation
            or reservation["offer_id"] != offer_id
            or reservation["status"] == "completed"
        ):
            raise HTTPException(409, "This booking does not need reconciliation")
        if reservation.get("created", time.time()) > time.time() - 120:
            raise HTTPException(
                409, "Allow two minutes for the original request to finish"
            )
        if settings.mode == "demo":
            db.remove(tenant, "reservation", key)
            return {
                "status": "released",
                "message": "Demo reservation released; no external event exists.",
            }
        event_id = hashlib.sha256((tenant + offer_id).encode()).hexdigest()
        gateway = calendar_gateway(tenant)
        try:
            event = (
                gateway.service.events()
                .get(calendarId=gateway.config.calendar_id, eventId=event_id)
                .execute()
            )
        except Exception as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status == 404:
                db.remove(tenant, "reservation", key)
                return {
                    "status": "released",
                    "message": "No event exists with this booking ID. The reservation was released.",
                }
            raise HTTPException(
                503, "Could not verify the external event. Reservation preserved."
            )
        if event.get("status") == "cancelled":
            db.remove(tenant, "reservation", key)
            return {
                "status": "released",
                "message": "The external event was cancelled; reservation released.",
            }
        if not all(k in reservation for k in ("meeting", "lead", "conversation")):
            raise HTTPException(
                409,
                "External event found, but local booking details need manual review",
            )
        meeting = {
            **reservation["meeting"],
            "external_event_id": event_id,
            "external_event_url": event.get("htmlLink"),
            "status": "booked",
        }
        with db.transaction(tenant) as c:
            current = db.get(tenant, "reservation", key, c)
            if not current or current["status"] == "completed":
                raise HTTPException(409, "This booking has already been reviewed")
            latest_lead = (
                db.get(tenant, "lead", reservation["lead"]["id"], c)
                or reservation["lead"]
            )
            lead = {**latest_lead, "stage": "meeting_booked", "meeting_requested": True}
            conv = (
                db.get(tenant, "conversation", reservation["conversation_id"], c)
                or reservation["conversation"]
            )
            conv["lead_id"] = lead["id"]
            conv["messages"].append(
                {
                    "id": uuid4().hex,
                    "role": "assistant",
                    "content": "Your consultation booking has been verified by the team.",
                    "created_at": now_iso(),
                }
            )
            conv["updated_at"] = now_iso()
            db.put(tenant, "meeting", offer_id, meeting, c)
            db.put(tenant, "lead", lead["id"], lead, c)
            db.put(tenant, "conversation", conv["id"], conv, c)
            db.put(
                tenant, "reservation", key, {**reservation, "status": "completed"}, c
            )
            enqueue_events(tenant, "meeting_booked", lead, offer_id, c)
        return {
            "status": "booked",
            "message": "External booking verified and local records restored.",
        }

    @app.post("/api/public/requests")
    def request_action(data: RequestInput, session=Depends(visitor)):
        def receipt(item):
            # Internal owner/outcome notes are never part of a visitor retry response.
            return {
                k: item[k]
                for k in (
                    "id",
                    "kind",
                    "lead_id",
                    "conversation_id",
                    "created_at",
                    "summary",
                )
            } | {"status": "recorded"}

        tenant, conv_id = session["tenant"], session["subject"]
        payload = data.model_dump(exclude={"request_id"})
        fingerprint = digest(json.dumps(payload, sort_keys=True))
        key = digest(conv_id + ":" + (data.request_id or fingerprint))
        with db.transaction(tenant) as c:
            previous = db.get(tenant, "request", key, c)
            if previous:
                if previous.get("fingerprint") != fingerprint:
                    raise HTTPException(
                        409,
                        "This request ID belongs to different details. Submit the changes with a new ID.",
                    )
                return receipt(previous)
            conv, lead = contact_lead(
                session,
                data,
                "request_proposal" if data.kind == "proposal" else "human_handover",
                c,
            )
            lead["stage"] = (
                "proposal_requested" if data.kind == "proposal" else "handover"
            )
            lead[
                (
                    "proposal_requested"
                    if data.kind == "proposal"
                    else "human_handover_requested"
                )
            ] = True
            if data.consent:
                record_consent(db, tenant, lead, "granted", "visitor_form", c)
            if data.kind == "handover" and conv["status"] != "human":
                conv["status"] = "handover_requested"
            result = {
                "id": key,
                "fingerprint": fingerprint,
                "kind": data.kind,
                "lead_id": lead["id"],
                "conversation_id": conv_id,
                "status": "recorded",
                "created_at": now_iso(),
                "summary": data.goal,
            }
            conv["messages"].append(
                {
                    "id": uuid4().hex,
                    "role": "assistant",
                    "content": "Your request has been recorded for the team. Email delivery is tracked separately.",
                    "created_at": now_iso(),
                }
            )
            conv["updated_at"] = now_iso()
            db.put(tenant, "request", key, result, c)
            db.put(tenant, "lead", lead["id"], lead, c)
            db.put(tenant, "conversation", conv_id, conv, c)
            enqueue_events(tenant, data.kind + "_requested", lead, key, c)
        return receipt(result)

    @app.get("/embed.js")
    def embed():
        return FileResponse(
            settings.frontend_dir / "public" / "embed.js",
            media_type="application/javascript",
        )

    if settings.static_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=settings.static_dir / "assets"),
            name="assets",
        )

    @app.get("/{path:path}")
    def frontend(path: str, request: Request):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        if not (settings.static_dir / "index.html").is_file():
            return PlainTextResponse(
                "API is running. Start the backend-connected frontend dev server or build its production bundle.",
                status_code=200,
            )
        result = FileResponse(settings.static_dir / "index.html")
        ancestors = ["'self'"]
        if path == "widget":
            b = business(request.query_params.get("business", "systematic"))
            ancestors += b["allowed_origins"]
        result.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors "
            + " ".join(ancestors)
        )
        return result

    return app


app = create_app()
