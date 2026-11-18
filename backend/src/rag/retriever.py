from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

from .models import RetrievedChunk, RetrievalRequest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = PROJECT_ROOT / ".env"


class RetrievalBackendError(RuntimeError):
    pass


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{float(value):.10g}" for value in values) + "]"


class SupabaseRAGRetriever:
    def __init__(
        self,
        supabase_url: str | None = None,
        supabase_secret_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        if supabase_url is None or supabase_secret_key is None:
            load_dotenv(ENV_PATH)
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL", "").strip()
        self.supabase_secret_key = supabase_secret_key or os.getenv("SUPABASE_SECRET_KEY", "").strip()
        if not self.supabase_url:
            raise RetrievalBackendError("SUPABASE_URL is missing")
        if not self.supabase_secret_key:
            raise RetrievalBackendError("SUPABASE_SECRET_KEY is missing")
        self.client = client or create_client(self.supabase_url, self.supabase_secret_key)

    def retrieve(self, request: RetrievalRequest, query_embedding: list[float]) -> list[RetrievedChunk]:
        response = self.client.rpc(
            "match_knowledge_chunks",
            {
                "query_embedding": vector_literal(query_embedding),
                "match_threshold": request.match_threshold,
                "match_count": request.match_count,
                "filter_content_type": request.content_type,
            },
        ).execute()
        rows = response.data or []
        chunks = [RetrievedChunk.from_rpc_row(row) for row in rows]
        return sorted(chunks, key=lambda chunk: chunk.similarity, reverse=True)
