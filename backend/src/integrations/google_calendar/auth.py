from __future__ import annotations

from pathlib import Path
from typing import Any
import errno
import os
import tempfile

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from .config import CALENDAR_SCOPES
from .errors import CalendarAuthenticationRequired, CalendarConfigurationError


def load_authorized_credentials(
    token_file: Path | None, scopes: tuple[str, ...] = CALENDAR_SCOPES
) -> Credentials:
    if not token_file or not token_file.exists():
        raise CalendarAuthenticationRequired("Google Calendar token file is missing")
    credentials = Credentials.from_authorized_user_file(str(token_file))
    if not credentials.has_scopes(scopes):
        raise CalendarAuthenticationRequired(
            "Google Calendar authorization is missing required scopes"
        )
    if credentials.valid:
        return credentials
    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
        except RefreshError as exc:
            raise CalendarAuthenticationRequired(
                "Google Calendar token refresh failed"
            ) from exc
        _save_credentials(token_file, credentials)
        return credentials
    raise CalendarAuthenticationRequired("Google Calendar authorization is required")


def validate_client_credentials_file(credentials_file: Path | None) -> Path:
    if not credentials_file or not credentials_file.exists():
        raise CalendarConfigurationError(
            "Google OAuth client credentials file is missing"
        )
    return credentials_file


def _save_credentials(token_file: Path, credentials: Credentials) -> None:
    # Refresh works with read-only secret mounts too. Persist atomically when writable.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=token_file.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(credentials.to_json())
        os.replace(temporary, token_file)
    except OSError as exc:
        if exc.errno not in (errno.EROFS, errno.EACCES, errno.EPERM):
            raise
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def safe_credentials_summary(credentials: Credentials) -> dict[str, Any]:
    return {
        "valid": bool(credentials.valid),
        "expired": bool(credentials.expired),
        "has_refresh_token": bool(credentials.refresh_token),
        "scopes": list(credentials.scopes or []),
    }
