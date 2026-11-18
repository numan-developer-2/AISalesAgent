from __future__ import annotations

from .models import ConversationMessage


def format_history(history: list[ConversationMessage], max_items: int = 10, max_chars: int = 2500) -> str:
    selected = history[-max_items:]
    lines: list[str] = []
    used = 0
    for item in selected:
        line = f"{item.role}: {item.content.strip()}"
        if used + len(line) > max_chars:
            break
        lines.append(line)
        used += len(line)
    return "\n".join(lines)
