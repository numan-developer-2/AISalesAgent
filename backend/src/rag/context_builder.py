from __future__ import annotations

from .models import RetrievedChunk


class RAGContextBuilder:
    def __init__(self, max_context_chars: int = 6000) -> None:
        if max_context_chars < 0:
            raise ValueError("max_context_chars must not be negative")
        self.max_context_chars = max_context_chars

    def build(self, chunks: list[RetrievedChunk]) -> str:
        parts: list[str] = []
        used = 0
        ordered = sorted(chunks, key=lambda chunk: chunk.similarity, reverse=True)
        for index, chunk in enumerate(ordered, start=1):
            separator_size = 2 if parts else 0
            remaining = self.max_context_chars - used - separator_size
            if remaining <= 0:
                break
            block = (
                f"[Source {index}]\n"
                f"Chunk ID: {chunk.chunk_id}\n"
                f"Title: {chunk.title or ''}\n"
                f"Type: {chunk.content_type or ''}\n"
                f"URL: {chunk.source_url or ''}\n"
                f"Similarity: {chunk.similarity:.6f}\n"
                "Content:\n"
                f"{chunk.content.strip()}\n"
            )
            if len(block) > remaining:
                block = block[:remaining].rstrip()
            if not block:
                break
            parts.append(block)
            used += len(block) + separator_size
            if used >= self.max_context_chars:
                break
        return "\n\n".join(parts)
