from __future__ import annotations

from .models import ALLOWED_ACTION_TYPES, ActionType, UnknownActionError


class ToolRegistry:
    def __init__(self, allowed: set[str] | None = None) -> None:
        self.allowed = allowed or set(ALLOWED_ACTION_TYPES)

    def validate(self, action_type: str) -> ActionType:
        if action_type not in self.allowed:
            raise UnknownActionError(f"unsupported action type: {action_type}")
        return action_type  # type: ignore[return-value]
