from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv
from supabase import create_client

from .models import ActionAuditEvent, ActionRequest


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ActionRepository(Protocol):
    def get_by_idempotency_key(self, idempotency_key: str) -> ActionRequest | None: ...
    def get_by_reference(self, action_reference: str) -> ActionRequest | None: ...
    def save(self, action: ActionRequest) -> ActionRequest: ...


class ActionAuditRepository(Protocol):
    def add(self, event: ActionAuditEvent) -> ActionAuditEvent: ...
    def list_for_action(self, action_id: str) -> list[ActionAuditEvent]: ...


class InMemoryActionRepository:
    def __init__(self) -> None:
        self.records: dict[str, ActionRequest] = {}

    def get_by_idempotency_key(self, idempotency_key: str) -> ActionRequest | None:
        return next((a for a in self.records.values() if a.idempotency_key == idempotency_key), None)

    def get_by_reference(self, action_reference: str) -> ActionRequest | None:
        return self.records.get(action_reference)

    def save(self, action: ActionRequest) -> ActionRequest:
        stored = action if action.id else ActionRequest(**{**action.__dict__, "id": action.action_reference})
        self.records[stored.action_reference] = stored
        return stored


class InMemoryActionAuditRepository:
    def __init__(self) -> None:
        self.records: list[ActionAuditEvent] = []

    def add(self, event: ActionAuditEvent) -> ActionAuditEvent:
        self.records.append(event)
        return event

    def list_for_action(self, action_id: str) -> list[ActionAuditEvent]:
        return [event for event in self.records if event.action_id == action_id]


class SupabaseActionRepository:
    def __init__(self) -> None:
        load_dotenv(PROJECT_ROOT / ".env")
        self.client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SECRET_KEY"))

    def get_by_idempotency_key(self, idempotency_key: str) -> ActionRequest | None:
        res = self.client.table("sales_actions").select("*").eq("idempotency_key", idempotency_key).limit(1).execute()
        return _action_from_record(res.data[0]) if res.data else None

    def get_by_reference(self, action_reference: str) -> ActionRequest | None:
        res = self.client.table("sales_actions").select("*").eq("action_reference", action_reference).limit(1).execute()
        return _action_from_record(res.data[0]) if res.data else None

    def save(self, action: ActionRequest) -> ActionRequest:
        row = {key: value.isoformat() if isinstance(value, datetime) else value for key, value in action.__dict__.items()}
        res = self.client.table("sales_actions").upsert(row, on_conflict="action_reference").execute()
        return _action_from_record(res.data[0]) if res.data else action


class SupabaseActionAuditRepository:
    def __init__(self) -> None:
        load_dotenv(PROJECT_ROOT / ".env")
        self.client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SECRET_KEY"))

    def add(self, event: ActionAuditEvent) -> ActionAuditEvent:
        self.client.table("sales_action_audit").insert({key: value.isoformat() if isinstance(value, datetime) else value for key, value in event.__dict__.items()}).execute()
        return event

    def list_for_action(self, action_id: str) -> list[ActionAuditEvent]:
        res = self.client.table("sales_action_audit").select("*").eq("action_id", action_id).execute()
        return [ActionAuditEvent(**row) for row in res.data or []]


def _action_from_record(row: dict) -> ActionRequest:
    allowed = {name for name in ActionRequest.__dataclass_fields__}
    values = {key: value for key, value in row.items() if key in allowed}
    for key in ("created_at", "updated_at", "confirmed_at", "completed_at", "expires_at"):
        if isinstance(values.get(key), str):
            values[key] = datetime.fromisoformat(values[key].replace("Z", "+00:00"))
    return ActionRequest(**values)
