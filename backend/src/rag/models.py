from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_MATCH_COUNT = 5
DEFAULT_MATCH_THRESHOLD = 0.50
MAX_MATCH_COUNT = 20
MAX_QUERY_LENGTH = 1000


class RetrievalValidationError(ValueError):
    pass


def normalize_query(query: object, max_length: int = MAX_QUERY_LENGTH) -> str:
    if not isinstance(query, str):
        raise RetrievalValidationError("query must be text")
    normalized = query.strip()
    if not normalized:
        raise RetrievalValidationError("query must not be empty")
    if len(normalized) > max_length:
        raise RetrievalValidationError(f"query must be {max_length} characters or fewer")
    return normalized


def clamp_match_count(match_count: int | None) -> int:
    if match_count is None:
        return DEFAULT_MATCH_COUNT
    return max(1, min(int(match_count), MAX_MATCH_COUNT))


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    match_count: int = DEFAULT_MATCH_COUNT
    match_threshold: float = DEFAULT_MATCH_THRESHOLD
    content_type: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "query", normalize_query(self.query))
        object.__setattr__(self, "match_count", clamp_match_count(self.match_count))
        object.__setattr__(self, "match_threshold", float(self.match_threshold))
        if self.content_type is not None:
            cleaned = str(self.content_type).strip()
            object.__setattr__(self, "content_type", cleaned or None)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    content: str
    title: str | None
    source_url: str | None
    content_type: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    similarity: float = 0.0

    @classmethod
    def from_rpc_row(cls, row: dict[str, Any]) -> "RetrievedChunk":
        return cls(
            chunk_id=str(row.get("chunk_id") or ""),
            content=str(row.get("content") or ""),
            title=row.get("title"),
            source_url=row.get("source_url"),
            content_type=row.get("content_type"),
            metadata=row.get("metadata") or {},
            similarity=float(row.get("similarity") or 0.0),
        )


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    chunks: list[RetrievedChunk]
    context: str

    @property
    def retrieved_count(self) -> int:
        return len(self.chunks)
