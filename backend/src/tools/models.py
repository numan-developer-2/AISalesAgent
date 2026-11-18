from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4


ActionType = Literal["check_meeting_availability", "book_meeting", "request_proposal", "human_handover"]
ActionStatus = Literal["requested", "awaiting_confirmation", "ready", "executing", "completed", "failed", "cancelled", "expired"]
ConfirmationStatus = Literal["not_required", "required", "confirmed", "rejected", "expired"]

SIDE_EFFECT_ACTIONS: set[str] = {"book_meeting", "request_proposal", "human_handover"}
ALLOWED_ACTION_TYPES: set[str] = {"check_meeting_availability", *SIDE_EFFECT_ACTIONS}
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "requested": {"awaiting_confirmation", "ready", "executing", "failed", "cancelled", "expired"},
    "awaiting_confirmation": {"ready", "cancelled", "expired", "failed"},
    "ready": {"executing", "cancelled", "expired", "failed"},
    "executing": {"completed", "failed"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
    "expired": set(),
}


class ActionError(RuntimeError):
    pass


class UnknownActionError(ActionError):
    pass


class InvalidActionTransition(ActionError):
    pass


class ConfirmationError(ActionError):
    pass


class ActionValidationError(ActionError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def safe_payload(value: dict[str, Any] | None) -> dict[str, Any]:
    blocked = ("api_key", "token", "authorization", "secret", "password", "hidden_prompt", "raw_rag_context")
    clean: dict[str, Any] = {}
    for key, item in (value or {}).items():
        if any(part in key.lower() for part in blocked):
            continue
        clean[key] = item
    return clean


@dataclass(frozen=True)
class ActionRequest:
    action_type: ActionType
    conversation_id: str
    idempotency_key: str
    action_reference: str = field(default_factory=lambda: f"act_{uuid4().hex[:12]}")
    id: str | None = None
    lead_id: str | None = None
    status: ActionStatus = "requested"
    requires_confirmation: bool = False
    confirmation_status: ConfirmationStatus = "not_required"
    payload: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    confirmed_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.action_type not in ALLOWED_ACTION_TYPES:
            raise UnknownActionError(f"unsupported action type: {self.action_type}")
        if self.requires_confirmation and self.confirmation_status == "not_required":
            object.__setattr__(self, "confirmation_status", "required")
        object.__setattr__(self, "payload", safe_payload(self.payload))
        object.__setattr__(self, "result", safe_payload(self.result))

    def transition(self, new_status: ActionStatus, **changes: Any) -> "ActionRequest":
        if new_status not in ALLOWED_TRANSITIONS[self.status]:
            raise InvalidActionTransition(f"invalid action transition: {self.status} -> {new_status}")
        updates = {"status": new_status, "updated_at": utc_now(), **changes}
        if new_status == "completed":
            updates["completed_at"] = updates["updated_at"]
        return replace(self, **updates)


@dataclass(frozen=True)
class ActionAuditEvent:
    action_id: str
    event_type: str
    previous_status: str | None = None
    new_status: str | None = None
    safe_metadata: dict[str, Any] = field(default_factory=dict)
    id: str | None = None
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "safe_metadata", safe_payload(self.safe_metadata))


@dataclass(frozen=True)
class ToolResult:
    success: bool
    action_reference: str
    status: str
    customer_message: str
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
