"""Durable automation worker. Run separately: python -m workspace.worker."""

from __future__ import annotations

import json
import smtplib
import ssl
import time
from email.message import EmailMessage
from pathlib import Path

import httpx
from workspace.config import Settings, ROOT, secret
from workspace.database import Database
from workspace.consent import is_suppressed


class NotConfigured(Exception):
    pass


def google_credentials(settings, tenant, variable, scopes):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    path = secret(settings, tenant, variable)
    if not path:
        raise NotConfigured("Google authorization is required")
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = ROOT / resolved
    if not resolved.is_file():
        raise NotConfigured("Google token file is missing")
    creds = Credentials.from_authorized_user_file(str(resolved))
    if not creds.has_scopes(scopes):
        raise NotConfigured("Google token does not have the required permissions")
    if not creds.valid:
        if not creds.refresh_token:
            raise NotConfigured("Google authorization must be renewed")
        creds.refresh(Request())
    return creds


def deliver(db, settings, job):
    tenant, kind = job["tenant"], job["kind"]
    payload = json.loads(job["payload"])
    business = db.get(tenant, "business", tenant)
    lead = db.get(tenant, "lead", payload.get("lead_id", ""))
    if not business or not lead:
        return "cancelled"
    if kind == "followup" and (
        lead.get("stage")
        in ("won", "lost", "meeting_booked", "meeting_attended", "handover")
        or lead.get("consent_status") != "granted"
        or is_suppressed(db, tenant, lead.get("email"))
    ):
        return "cancelled"
    if kind == "followup":
        from datetime import datetime

        conversation = db.get(tenant, "conversation", lead.get("conversation_id", ""))
        if conversation and any(
            datetime.fromisoformat(m["created_at"]).timestamp() > job["created"]
            for m in conversation.get("messages", [])
        ):
            return "cancelled"
    if settings.mode == "demo":
        return "simulated"
    integration = "email" if kind in ("email", "followup") else kind
    if not business.get("integrations", {}).get(integration):
        raise NotConfigured(f"{integration} integration is disabled")
    if kind in ("email", "followup"):
        host = secret(settings, tenant, "SMTP_HOST")
        sender = secret(settings, tenant, "SMTP_FROM")
        recipient = (
            lead.get("email")
            if kind == "followup"
            else business.get("notification_email")
        )
        if not host or not sender or not recipient:
            raise NotConfigured("Configure SMTP sender and notification recipient")
        msg = EmailMessage()
        msg["From"], msg["To"] = sender, recipient
        msg["Subject"] = f"{business['name']}: " + (
            "Following up on your inquiry"
            if kind == "followup"
            else payload.get("event", "New inquiry").replace("_", " ")
        )
        msg["Message-ID"] = f"<{job['id']}@{sender.split('@')[-1]}>"
        if kind == "followup":
            msg.set_content(
                f"Hello {lead.get('full_name') or 'there'},\n\nYou contacted {business['name']} about {', '.join(lead.get('required_services', []))}. If you'd like to continue, reply to this email and our team will help.\n\nIf you don't want further follow-ups, reply 'stop'."
            )
        else:
            msg.set_content(
                f"{lead.get('full_name','Visitor')} | {lead.get('company_name','')}\nService: {', '.join(lead.get('required_services', []))}\nEmail: {lead.get('email','')}\nNeed: {lead.get('business_goal','')}\nPriority: {lead.get('lead_classification','')}\nNext action: {lead.get('next_action','')}\nOpen the sales workspace to review this inquiry."
            )
        port = int(secret(settings, tenant, "SMTP_PORT") or "587")
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            user, password = secret(settings, tenant, "SMTP_USER"), secret(
                settings, tenant, "SMTP_PASSWORD"
            )
            if user:
                smtp.login(user, password)
            # Consent can change while SMTP connects/authenticates.
            if kind == "followup":
                latest = db.get(tenant, "lead", lead["id"])
                if (
                    not latest
                    or latest.get("consent_status") != "granted"
                    or is_suppressed(db, tenant, latest.get("email"))
                    or latest.get("stage")
                    in ("won", "lost", "meeting_booked", "meeting_attended", "handover")
                ):
                    return "cancelled"
            smtp.send_message(msg)
    elif kind == "sheets":
        from googleapiclient.discovery import build

        sheet = secret(settings, tenant, "GOOGLE_SHEET_ID")
        if not sheet:
            raise NotConfigured("Spreadsheet ID is missing")
        creds = google_credentials(
            settings,
            tenant,
            "GOOGLE_SHEETS_TOKEN_FILE",
            ["https://www.googleapis.com/auth/spreadsheets"],
        )
        api = (
            build("sheets", "v4", credentials=creds, cache_discovery=False)
            .spreadsheets()
            .values()
        )
        # Stable lead ID is the first column; retries update the existing row.
        rows = (
            api.get(spreadsheetId=sheet, range="Leads!A:A").execute().get("values", [])
        )
        index = next(
            (i + 1 for i, row in enumerate(rows) if row and row[0] == lead["id"]), None
        )
        values = [
            [
                lead["id"],
                lead.get("full_name", ""),
                lead.get("company_name", ""),
                lead.get("email", ""),
                ", ".join(lead.get("required_services", [])),
                lead.get("lead_score", 0),
                lead.get("stage", ""),
                lead.get("updated_at", ""),
            ]
        ]
        if index:
            api.update(
                spreadsheetId=sheet,
                range=f"Leads!A{index}:H{index}",
                valueInputOption="RAW",
                body={"values": values},
            ).execute()
        else:
            api.append(
                spreadsheetId=sheet,
                range="Leads!A:H",
                valueInputOption="RAW",
                body={"values": values},
            ).execute()
    elif kind == "crm":
        # A generic webhook contract; client-specific field mapping belongs in an adapter.
        url, key = secret(settings, tenant, "CRM_WEBHOOK_URL"), secret(
            settings, tenant, "CRM_API_KEY"
        )
        if not url or not url.startswith("https://") or not key:
            raise NotConfigured("Configure an HTTPS CRM webhook and API key")
        response = httpx.post(
            url,
            json={"event": payload.get("event"), "lead": lead},
            headers={"Authorization": f"Bearer {key}", "Idempotency-Key": job["id"]},
            timeout=20,
            follow_redirects=False,
        )
        response.raise_for_status()
    else:
        raise NotConfigured("No delivery adapter for this job type")
    return "completed"


def process_one(db, settings, tenant=None):
    job = db.claim_job(tenant)
    if not job:
        return False
    try:
        state = deliver(db, settings, job)
        db.finish_job(job, state)
    except NotConfigured as exc:
        db.finish_job(job, "blocked", str(exc))
    except Exception:
        # Do not persist provider response bodies, credentials, contact data or stack traces.
        db.finish_job(
            job,
            "failed" if job["attempts"] >= 5 else "pending",
            "Delivery failed. Check service authorization and connectivity.",
        )
    return True


def main():
    settings = Settings()
    db = Database(settings.database_url)
    print(
        f"Automation worker started in {settings.mode} mode. Press Ctrl+C to stop.",
        flush=True,
    )
    try:
        while True:
            if not process_one(db, settings):
                time.sleep(2)
    except KeyboardInterrupt:
        print("Worker stopped.")


if __name__ == "__main__":
    main()
