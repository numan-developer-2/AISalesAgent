from __future__ import annotations

from agents.models import ConversationMessage

from .models import SalesMessage


def bounded_history(messages: list[SalesMessage], limit: int = 10) -> list[ConversationMessage]:
    return [message.to_history() for message in messages if message.role in ("user", "assistant")][-limit:]
