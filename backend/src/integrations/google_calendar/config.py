from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[4]
CALENDAR_SCOPES = (
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.events.freebusy",
)


@dataclass(frozen=True)
class GoogleCalendarConfig:
    enabled: bool = False
    calendar_id: str = ""
    timezone: str = "Asia/Karachi"
    credentials_file: Path | None = None
    token_file: Path | None = None
    scopes: tuple[str, ...] = CALENDAR_SCOPES

    @classmethod
    def from_env(cls) -> "GoogleCalendarConfig":
        credentials = os.getenv("GOOGLE_CALENDAR_CREDENTIALS_FILE", "").strip()
        token = os.getenv("GOOGLE_CALENDAR_TOKEN_FILE", "").strip()
        return cls(
            enabled=os.getenv("GOOGLE_CALENDAR_ENABLED", "false").strip().lower() == "true",
            calendar_id=os.getenv("GOOGLE_CALENDAR_ID", "").strip(),
            timezone=os.getenv("GOOGLE_CALENDAR_TIMEZONE", "Asia/Karachi").strip() or "Asia/Karachi",
            credentials_file=_resolve(credentials) if credentials else None,
            token_file=_resolve(token) if token else None,
        )


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path
