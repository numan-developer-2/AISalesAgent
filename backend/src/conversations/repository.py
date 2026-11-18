from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv
from supabase import create_client

from .models import SalesConversation, SalesMessage


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ConversationRepository(Protocol):
    def get_by_key(self, conversation_key: str) -> SalesConversation | None: ...
    def upsert(self, conversation: SalesConversation) -> SalesConversation: ...


class MessageRepository(Protocol):
    def list_recent(self, conversation_id: str, limit: int) -> list[SalesMessage]: ...
    def add(self, message: SalesMessage) -> SalesMessage: ...


class InMemoryConversationRepository:
    def __init__(self) -> None:
        self.records: dict[str, SalesConversation] = {}

    def get_by_key(self, conversation_key: str) -> SalesConversation | None:
        return self.records.get(conversation_key)

    def upsert(self, conversation: SalesConversation) -> SalesConversation:
        stored = conversation if conversation.id else SalesConversation(**{**conversation.__dict__, "id": conversation.conversation_key})
        self.records[stored.conversation_key] = stored
        return stored


class InMemoryMessageRepository:
    def __init__(self) -> None:
        self.records: list[SalesMessage] = []

    def list_recent(self, conversation_id: str, limit: int) -> list[SalesMessage]:
        return [m for m in self.records if m.conversation_id == conversation_id][-limit:]

    def add(self, message: SalesMessage) -> SalesMessage:
        if message.role not in ("user", "assistant"):
            raise ValueError("message role must be user or assistant")
        self.records.append(message)
        return message


class SupabaseConversationRepository:
    def __init__(self) -> None:
        load_dotenv(PROJECT_ROOT / ".env")
        self.client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SECRET_KEY"))

    def get_by_key(self, conversation_key: str) -> SalesConversation | None:
        res = self.client.table("sales_conversations").select("*").eq("conversation_key", conversation_key).limit(1).execute()
        return _conversation_from_record(res.data[0]) if res.data else None

    def upsert(self, conversation: SalesConversation) -> SalesConversation:
        row = {
            "conversation_key": conversation.conversation_key,
            "lead_id": conversation.lead_id,
            "status": conversation.status,
            "language": conversation.language,
            "source_page": conversation.source_page,
        }
        res = self.client.table("sales_conversations").upsert(row, on_conflict="conversation_key").execute()
        return _conversation_from_record(res.data[0]) if res.data else conversation


class SupabaseMessageRepository:
    def __init__(self) -> None:
        load_dotenv(PROJECT_ROOT / ".env")
        self.client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SECRET_KEY"))

    def list_recent(self, conversation_id: str, limit: int) -> list[SalesMessage]:
        res = self.client.table("sales_messages").select("*").eq("conversation_id", conversation_id).order("created_at", desc=False).limit(limit).execute()
        return [_message_from_record(row) for row in res.data or []]

    def add(self, message: SalesMessage) -> SalesMessage:
        row = {
            "conversation_id": message.conversation_id,
            "role": message.role,
            "content": message.content,
            "intent": message.intent,
            "grounding_status": message.grounding_status,
            "grounding_sources": message.grounding_sources,
            "recommended_services": message.recommended_services,
            "requires_action": message.requires_action,
            "action_intent": message.action_intent,
            "source_metadata": [source.__dict__ for source in message.source_metadata],
        }
        self.client.table("sales_messages").insert(row).execute()
        return message


def _conversation_from_record(row: dict) -> SalesConversation:
    return SalesConversation(
        id=row.get("id"),
        conversation_key=row["conversation_key"],
        lead_id=row.get("lead_id"),
        status=row.get("status", "active"),
        language=row.get("language"),
        source_page=row.get("source_page"),
    )


def _message_from_record(row: dict) -> SalesMessage:
    return SalesMessage(
        conversation_id=row["conversation_id"],
        role=row["role"],
        content=row["content"],
        intent=row.get("intent"),
        grounding_status=row.get("grounding_status"),
        grounding_sources=row.get("grounding_sources", []),
        recommended_services=row.get("recommended_services", []),
        requires_action=row.get("requires_action", False),
        action_intent=row.get("action_intent"),
        source_metadata=[],
    )
