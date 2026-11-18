"""Deterministic contact suppression, independent of model availability."""

import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, update
from workspace.database import jobs


def requests_optout(message):
    return bool(
        re.search(
            r"\b(unsubscribe|stop (?:emailing|emails|messaging)|do not (?:email|contact)|don't (?:email|contact)|email mat (?:karo|karen)|emails? band (?:karo|karen))\b|ای میل.*(?:بند|مت)",
            message,
            re.I,
        )
    )


def contact_key(email):
    return hashlib.sha256((email or "").strip().lower().encode()).hexdigest()


def is_suppressed(db, tenant, email, conn=None):
    if not email:
        return False
    record = db.get(tenant, "suppression", contact_key(email), conn)
    return bool(record and record.get("active"))


def record_consent(db, tenant, lead, status, source, conn, allow_resubscribe=False):
    email = lead.get("email")
    if (
        status == "granted"
        and is_suppressed(db, tenant, email, conn)
        and not allow_resubscribe
    ):
        status = "declined"
    stamp = datetime.now(timezone.utc).isoformat()
    lead.update(consent_status=status, consent_updated_at=stamp, consent_source=source)
    proof = {
        "id": uuid4().hex,
        "lead_id": lead["id"],
        "status": status,
        "source": source,
        "created_at": stamp,
    }
    db.put(tenant, "consent_event", proof["id"], proof, conn)
    if email and (status == "declined" or status == "granted" and allow_resubscribe):
        db.put(
            tenant,
            "suppression",
            contact_key(email),
            {"active": status == "declined", "updated_at": stamp, "source": source},
            conn,
        )
    if status == "declined":
        related = {lead["id"]}
        if email:
            related.update(
                l["id"]
                for l in db.list(tenant, "lead", conn)
                if l.get("email") == email
            )
        for row in conn.execute(
            select(jobs.c.id, jobs.c.payload).where(
                jobs.c.tenant == tenant,
                jobs.c.kind == "followup",
                jobs.c.status.in_(["pending", "blocked", "failed"]),
            )
        ):
            if json.loads(row.payload).get("lead_id") in related:
                conn.execute(
                    update(jobs)
                    .where(jobs.c.id == row.id)
                    .values(status="cancelled", error=None)
                )
    return lead
