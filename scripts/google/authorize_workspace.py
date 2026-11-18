"""Operator-run OAuth setup for Calendar or Sheets; never runs during startup."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from integrations.google_calendar.config import CALENDAR_SCOPES

SCOPES = {
    "calendar": list(CALENDAR_SCOPES),
    "sheets": ["https://www.googleapis.com/auth/spreadsheets"],
}


def authorize(service: str, client_file: Path, token_file: Path, replace=False):
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_file, token_file = client_file.resolve(), token_file.resolve()
    if client_file == token_file:
        raise ValueError("Client credentials and token must use different files")
    if token_file.exists() and not replace:
        raise ValueError("Token already exists; use --replace only to reauthorize it")
    try:
        client = json.loads(client_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError("Cannot read a valid OAuth client JSON file") from None
    if not isinstance(client, dict) or "installed" not in client:
        raise ValueError("Download a Desktop app OAuth client JSON file")
    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_file), scopes=SCOPES[service]
    )
    credentials = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    if not credentials.refresh_token or not credentials.has_scopes(SCOPES[service]):
        raise ValueError("Required permissions or offline access were not granted")
    token_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=token_file.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(credentials.to_json())
        if replace:
            os.replace(temporary, token_file)
        else:
            # Exclusive creation prevents an intervening authorization being overwritten.
            os.link(temporary, token_file)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=SCOPES)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--token", type=Path, required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args(argv)
    try:
        authorize(args.service, args.client, args.token, args.replace)
    except (ValueError, FileExistsError) as exc:
        print(f"Setup incomplete: {exc}")
        return 1
    except Exception:
        # OAuth errors can contain authorization URLs or secrets; never print raw errors.
        print(
            "Authorization failed. Check the Google account, API access and connectivity."
        )
        return 1
    print(f"{args.service.title()} authorization saved. Keep the token file private.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
