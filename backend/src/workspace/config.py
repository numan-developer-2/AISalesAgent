from __future__ import annotations

import json
import os
import re
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[3]


def environment() -> dict[str, str]:
    # Only valid variable names are accepted. Never log source .env contents.
    values = {
        k: v
        for k, v in dotenv_values(ROOT / ".env").items()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k) and v is not None
    }
    return {**values, **os.environ}


class Settings:
    def __init__(self, mode: str | None = None, database_url: str | None = None):
        self.env = environment()
        self.mode = mode or self.env.get("APP_MODE", "demo")
        if self.mode not in ("demo", "live"):
            raise ValueError("APP_MODE must be demo or live")
        runtime = ROOT / "data" / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        self.database_url = (
            database_url
            or self.env.get("APP_DATABASE_URL")
            or f'sqlite:///{(runtime / (self.mode + ".db")).as_posix()}'
        )
        self.secure_cookies = self.env.get("COOKIE_SECURE", "false").lower() == "true"
        self.origin = self.env.get("APP_ORIGIN", "http://localhost:5173").rstrip("/")
        self.origins = (
            list(
                dict.fromkeys(
                    [self.origin, "http://localhost:8000", "http://127.0.0.1:8000"]
                )
            )
            if self.mode == "demo"
            else [self.origin]
        )
        self.business_dir = Path(
            self.env.get("BUSINESS_CONFIG_DIR", str(ROOT / "config" / "businesses"))
        )
        # Support both the private nested checkout and the public root frontend.
        self.frontend_dir = (
            ROOT / "frontend" / "app"
            if (ROOT / "frontend" / "app" / "package.json").is_file()
            else ROOT
        )
        self.static_dir = self.frontend_dir / "dist"
        if self.mode == "live" and (
            not self.secure_cookies or not self.origin.startswith("https://")
        ):
            raise ValueError(
                "Live mode requires COOKIE_SECURE=true and an HTTPS APP_ORIGIN"
            )


def validate_business(data: dict) -> dict:
    from workspace.business_schema import BusinessConfig

    return BusinessConfig.model_validate(data).model_dump()


def initial_businesses(settings: Settings):
    return [
        validate_business(json.loads(p.read_text(encoding="utf-8")))
        for p in sorted(settings.business_dir.glob("*.json"))
    ]


def secret(settings: Settings, tenant: str, name: str) -> str:
    # New businesses get independent credential namespaces; never inherit another tenant's keys.
    prefix = tenant.upper().replace("-", "_")
    return settings.env.get(f"{prefix}_{name}", "") or (
        settings.env.get(name, "") if tenant == "systematic" else ""
    )
