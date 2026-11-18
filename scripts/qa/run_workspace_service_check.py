"""Report configuration presence and optionally probe Calendar without creating events."""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend/src"))
from workspace.config import Settings, secret


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--business", default="systematic")
    parser.add_argument("--calendar-readonly", action="store_true")
    args = parser.parse_args()
    settings = Settings(mode="demo")
    values = lambda key: secret(settings, args.business, key)
    report = {
        "business": args.business,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "configured": {key: bool(values(key)) for key in (
            "ADMIN_EMAIL", "ADMIN_PASSWORD_HASH", "GEMINI_API_KEY",
            "GOOGLE_CALENDAR_ID", "GOOGLE_CALENDAR_TOKEN_FILE", "SMTP_HOST",
            "SMTP_FROM", "GOOGLE_SHEET_ID", "GOOGLE_SHEETS_TOKEN_FILE",
            "CRM_WEBHOOK_URL", "CRM_API_KEY",
        )},
        "calendar": {"status": "not_tested"},
        "external_events_created": 0,
        "outbound_messages": 0,
        "credential_files_modified": False,
    }
    if args.calendar_readonly:
        try:
            import requests
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from integrations.google_calendar.config import CALENDAR_SCOPES

            token = values("GOOGLE_CALENDAR_TOKEN_FILE")
            calendar = values("GOOGLE_CALENDAR_ID")
            if not token or not calendar:
                report["calendar"] = {"status": "not_configured"}
            else:
                path = Path(token)
                if not path.is_absolute():
                    path = ROOT / path
                credentials = Credentials.from_authorized_user_file(str(path))
                if not credentials.has_scopes(CALENDAR_SCOPES):
                    raise ValueError("Required Calendar scopes are absent")
                if not credentials.valid:
                    transport = Request()

                    def bounded_request(*args, **kwargs):
                        kwargs["timeout"] = 15
                        return transport(*args, **kwargs)

                    credentials.refresh(bounded_request)
                start = datetime.now(timezone.utc) + timedelta(days=2)
                response = requests.post(
                    "https://www.googleapis.com/calendar/v3/freeBusy",
                    headers={"Authorization": "Bearer " + credentials.token},
                    json={"timeMin": start.isoformat(),
                          "timeMax": (start + timedelta(hours=1)).isoformat(),
                          "items": [{"id": calendar}]},
                    timeout=15,
                )
                payload = response.json() if response.status_code == 200 else {}
                row = payload.get("calendars", {}).get(calendar)
                passed = row is not None and not row.get("errors")
                report["calendar"] = {
                    "status": "freebusy_passed" if passed else "failed",
                    "http_status": response.status_code,
                }
        except Exception as exc:
            report["calendar"] = {"status": "failed", "error_type": type(exc).__name__}
    folder = ROOT / "artifacts" / "backend-service-qa" / uuid4().hex
    folder.mkdir(parents=True)
    path = folder / "result.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({**report, "report": str(path)}), flush=True)
    return 0 if report["calendar"]["status"] in ("not_tested", "freebusy_passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
