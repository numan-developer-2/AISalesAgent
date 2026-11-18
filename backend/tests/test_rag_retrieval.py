from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest


BACKEND_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(BACKEND_SRC))

from rag.context_builder import RAGContextBuilder
from rag.models import RetrievedChunk, RetrievalRequest, RetrievalValidationError, normalize_query
from rag.query_embedding import format_query_for_embedding, validate_embedding_vector
from rag.retriever import SupabaseRAGRetriever
from rag.service import RAGRetrievalService


def test_empty_query_rejected() -> None:
    with pytest.raises(RetrievalValidationError):
        normalize_query("   ")


def test_query_formatting_correct() -> None:
    assert format_query_for_embedding("  SEO pricing? ") == "task: search result | query: SEO pricing?"


def test_dimension_validation() -> None:
    with pytest.raises(RuntimeError):
        validate_embedding_vector([0.1, 0.2], 768)
    with pytest.raises(RuntimeError):
        validate_embedding_vector([math.nan] * 768, 768)


def test_match_count_clamping() -> None:
    assert RetrievalRequest("seo", match_count=999).match_count == 20
    assert RetrievalRequest("seo", match_count=0).match_count == 1


def test_no_result_behavior() -> None:
    class Embedder:
        def embed_query(self, query: str) -> list[float]:
            return [0.1] * 768

    class Retriever:
        def retrieve(self, request: RetrievalRequest, query_embedding: list[float]) -> list[RetrievedChunk]:
            return []

    result = RAGRetrievalService(embedder=Embedder(), retriever=Retriever()).retrieve("unrelated query")
    assert result.retrieved_count == 0
    assert result.chunks == []
    assert result.context == ""


def test_retrieved_row_normalization() -> None:
    chunk = RetrievedChunk.from_rpc_row(
        {
            "id": 99,
            "chunk_id": "chunk_1",
            "content": "Source text",
            "title": "Title",
            "source_url": "https://example.test",
            "content_type": "faq",
            "metadata": {"safe": True},
            "similarity": 0.75,
        }
    )
    assert chunk.chunk_id == "chunk_1"
    assert chunk.similarity == 0.75
    assert not hasattr(chunk, "id")


def test_context_builder_ordering_and_source_urls() -> None:
    chunks = [
        RetrievedChunk("b", "Second", "B", "https://b.test", "faq", similarity=0.60),
        RetrievedChunk("a", "First", "A", "https://a.test", "faq", similarity=0.90),
    ]
    context = RAGContextBuilder().build(chunks)
    assert context.index("https://a.test") < context.index("https://b.test")
    assert "Chunk ID: a" in context
    assert "URL: https://a.test" in context


def test_content_type_filter_propagation() -> None:
    calls = {}

    class RpcCall:
        data = []

        def execute(self):
            return self

    class Client:
        def rpc(self, name, payload):
            calls["name"] = name
            calls["payload"] = payload
            return RpcCall()

    retriever = SupabaseRAGRetriever(
        supabase_url="https://example.supabase.co",
        supabase_secret_key="server-secret",
        client=Client(),
    )
    retriever.retrieve(RetrievalRequest("seo", content_type="faq"), [0.1] * 768)
    assert calls["name"] == "match_knowledge_chunks"
    assert calls["payload"]["filter_content_type"] == "faq"


def test_credentials_not_in_returned_models() -> None:
    result = RAGRetrievalService(
        embedder=type("Embedder", (), {"embed_query": lambda self, query: [0.1] * 768})(),
        retriever=type(
            "Retriever",
            (),
            {
                "retrieve": lambda self, request, query_embedding: [
                    RetrievedChunk("chunk", "content", "title", "url", "faq", similarity=0.7)
                ]
            },
        )(),
    ).retrieve("seo")
    serialized = repr(result)
    assert "GEMINI_API_KEY" not in serialized
    assert "SUPABASE_SECRET_KEY" not in serialized
    assert "server-secret" not in serialized
