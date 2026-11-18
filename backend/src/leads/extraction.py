from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import LeadUpdate


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:(?:\+?\d[\d\s().-]{7,}\d))")
DOMAIN_RE = re.compile(r"\b(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+\b", re.IGNORECASE)


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    match = EMAIL_RE.search(value.strip())
    return match.group(0).lower() if match else None


def normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    match = PHONE_RE.search(value)
    if not match:
        return None
    phone = re.sub(r"\s+", " ", match.group(0).strip())
    digits = re.sub(r"\D", "", phone)
    return phone if len(digits) >= 8 else None


def normalize_website(value: str | None) -> str | None:
    if not value:
        return None
    match = DOMAIN_RE.search(value.strip())
    if not match:
        return None
    url = match.group(0)
    if "@" in url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    return url if parsed.netloc and "." in parsed.netloc else None


def validate_lead_update(raw: dict) -> LeadUpdate:
    return LeadUpdate(
        full_name=_clean(raw.get("full_name")),
        company_name=_clean(raw.get("company_name")),
        email=normalize_email(raw.get("email")),
        phone=normalize_phone(raw.get("phone")),
        website_url=normalize_website(raw.get("website_url")),
        industry=_clean(raw.get("industry")),
        required_services=[_clean(item) for item in raw.get("required_services", []) if _clean(item)],
        business_goal=_clean(raw.get("business_goal")),
        budget_range=_clean(raw.get("budget_range")),
        timeline=_clean(raw.get("timeline")),
        authority_status=_clean(raw.get("authority_status")),
    )


def _clean(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None
