from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str


@dataclass(frozen=True)
class LLMRequest:
    system_prompt: str
    user_prompt: str
    response_schema: dict[str, Any]
    model: str | None = None


@dataclass(frozen=True)
class LLMResponse:
    data: dict[str, Any]
    model: str
    raw_text: str | None = field(default=None, repr=False)
