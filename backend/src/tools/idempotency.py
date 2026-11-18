from __future__ import annotations

import hashlib


def stable_idempotency_key(prefix: str, *parts: object) -> str:
    raw = ":".join(str(part or "none").strip().lower() for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


def booking_key(conversation_id: str, slot_id: str) -> str:
    return stable_idempotency_key("booking", conversation_id, slot_id)


def proposal_key(conversation_id: str, lead_revision: object) -> str:
    return stable_idempotency_key("proposal", conversation_id, lead_revision)


def handover_key(conversation_id: str, request_revision: object) -> str:
    return stable_idempotency_key("handover", conversation_id, request_revision)
