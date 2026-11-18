from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = PROJECT_ROOT / "backend" / "src"
sys.path.insert(0, str(BACKEND_SRC))

from integrations.google_calendar.config import CALENDAR_SCOPES, GoogleCalendarConfig
from integrations.google_calendar.auth import validate_client_credentials_file


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    config = GoogleCalendarConfig.from_env()
    credentials_file = validate_client_credentials_file(config.credentials_file)
    if not config.token_file:
        print("FAIL: GOOGLE_CALENDAR_TOKEN_FILE is required")
        return 1
    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), scopes=list(CALENDAR_SCOPES))
    credentials = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    config.token_file.parent.mkdir(parents=True, exist_ok=True)
    config.token_file.write_text(credentials.to_json(), encoding="utf-8")
    print("Google Calendar OAuth authorization complete.")
    print(f"Token saved to: {config.token_file}")
    print("Scopes authorized:")
    for scope in CALENDAR_SCOPES:
        print(f"- {scope}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
