from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import re

from .models import ActionRequest, ConfirmationError, utc_now


EXPLICIT_CONFIRMATION_PHRASES = (
    "yes",
    "confirm",
    "confirmed",
    "book it",
    "book this",
    "book that",
    "please book",
    "go ahead",
)
AMBIGUOUS_PHRASES = ("might work", "maybe", "prefer", "what times", "available", "could work")


def looks_explicit_confirmation(message: str) -> bool:
    text = " ".join(message.lower().strip().split())
    if not text or any(phrase in text for phrase in AMBIGUOUS_PHRASES):
        return False
    if re.search(r"\b(no|not|never|cancel|don't|dont|cannot|can't|isn't|wasn't)\b", text):
        return False
    if "?" in text:
        return False
    return any(re.search(r"\b" + re.escape(phrase) + r"\b", text) for phrase in EXPLICIT_CONFIRMATION_PHRASES)


class ConfirmationGuard:
    def confirm_slot(
        self,
        action: ActionRequest,
        message: str,
        slot_id: str,
        now: datetime | None = None,
    ) -> ActionRequest:
        current = now or utc_now()
        if action.status != "awaiting_confirmation" or action.confirmation_status != "required":
            raise ConfirmationError("action is not awaiting confirmation")
        if action.expires_at and current > action.expires_at:
            return action.transition("expired", confirmation_status="expired")
        offered_slot = action.payload.get("selected_slot_id")
        offered_slots = set(action.payload.get("offered_slot_ids", []))
        if not slot_id or slot_id != offered_slot or slot_id not in offered_slots:
            raise ConfirmationError("confirmation does not match current offered slot")
        if not looks_explicit_confirmation(message):
            raise ConfirmationError("confirmation language is not explicit")
        return replace(
            action.transition("ready"),
            confirmation_status="confirmed",
            confirmed_at=current,
            updated_at=current,
        )
