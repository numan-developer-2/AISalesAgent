from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from agents.models import ConversationMessage, SourceMetadata


@dataclass(frozen=True)
class SalesConversation:
    conversation_key: str
    id: str | None = None
    lead_id: str | None = None
    status: Literal["active", "closed", "handover_requested"] = "active"
    language: str | None = None
    source_page: str | None = None


@dataclass(frozen=True)
class SalesMessage:
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    intent: str | None = None
    grounding_status: str | None = None
    grounding_sources: list[str] = field(default_factory=list)
    recommended_services: list[str] = field(default_factory=list)
    requires_action: bool = False
    action_intent: str | None = None
    source_metadata: list[SourceMetadata] = field(default_factory=list)

    def to_history(self) -> ConversationMessage:
        return ConversationMessage(role=self.role, content=self.content)
