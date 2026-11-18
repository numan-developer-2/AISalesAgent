"""Regression checks for bounded HTTP/RAG work and readable demo output."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rag.context_builder import RAGContextBuilder
from rag.models import RetrievedChunk
from rag.query_embedding import GeminiQueryEmbedder
from workspace.engine import excerpt, respond
from workspace.http_limits import RequestBodyLimitMiddleware
from test_workspace_runtime import app, client


def test_chunked_upload_stops_at_limit_without_reading_the_remaining_stream():
    calls = []
    messages = iter([
        {"type": "http.request", "body": b"a" * 40000, "more_body": True},
        {"type": "http.request", "body": b"b" * 30000, "more_body": True},
    ])
    output = []

    async def receive():
        calls.append(1)
        return next(messages)  # A third read would fail this test.

    async def send(message):
        output.append(message)

    async def endpoint(*args):
        pytest.fail("Oversized input must not reach an endpoint")

    asyncio.run(RequestBodyLimitMiddleware(endpoint)(
        {"type": "http", "path": "/api/public/chat", "method": "POST"},
        receive, send,
    ))
    assert len(calls) == 2
    assert output[0]["status"] == 413


def test_body_limit_preserves_valid_json_and_rejects_oversized_api_input(client):
    assert client.post("/api/auth/demo", json={"business": "systematic"}).status_code == 200
    result = client.post("/api/auth/demo", content=b" " * 65537)
    assert result.status_code == 413
    assert result.headers["cache-control"] == "no-store"
    assert client.get("/api/admin/workspace").status_code == 200


@pytest.mark.parametrize("budget", [0, 1, 100, 210, 300, 6000])
def test_rag_context_counts_source_separators_inside_its_budget(budget):
    chunks = [
        RetrievedChunk(str(i), "Approved content. " * 30, "Title", "https://example.com", "faq", similarity=1 - i / 10)
        for i in range(5)
    ]
    assert len(RAGContextBuilder(budget).build(chunks)) <= budget


def test_embedding_has_transport_timeout_and_no_hidden_sdk_retries(monkeypatch):
    factory = Mock()
    monkeypatch.setattr("rag.query_embedding.genai.Client", factory)
    GeminiQueryEmbedder(api_key="fake", model="gemini-embedding-2", dimension=768)
    options = factory.call_args.kwargs["http_options"]
    assert options.timeout == 20000
    assert options.retry_options.attempts == 1


def test_interactive_vector_retrieval_uses_single_attempt_and_stays_tenant_scoped(app, monkeypatch):
    embedder = Mock(return_value=object())
    retriever = Mock(return_value=object())
    service = Mock(return_value=SimpleNamespace(retrieve=Mock(side_effect=RuntimeError("offline"))))
    monkeypatch.setattr("rag.query_embedding.GeminiQueryEmbedder", embedder)
    monkeypatch.setattr("rag.retriever.SupabaseRAGRetriever", retriever)
    monkeypatch.setattr("rag.service.RAGRetrievalService", service)
    settings = SimpleNamespace(mode="live", env={
        "SYSTEMATIC_GEMINI_API_KEY": "scoped-fake",
        "RAG_PROVIDER": "supabase",
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SECRET_KEY": "fake-test-only",
    })
    db = app.state.db
    with pytest.raises(RuntimeError, match="offline"):
        respond(db, settings, db.get("systematic", "business", "systematic"), "Explain SEO", [])
    assert embedder.call_args.kwargs == {"api_key": "scoped-fake", "max_retries": 1}
    service.reset_mock()
    with pytest.raises(RuntimeError, match="not configured"):
        respond(db, settings, db.get("second", "business", "second"), "Explain SEO", [])
    service.assert_not_called()


def test_demo_excerpts_end_at_sentences_or_words():
    assert excerpt("Short answer.", 30) == "Short answer."
    assert excerpt("One short sentence. Another unfinished thought", 30) == "One short sentence."
    assert excerpt("Explore meaningful conversations with prospects", 26) == "Explore meaningful…"
    assert excerpt("a" * 100, 20) == "…"


def test_provider_failure_releases_chat_lock_and_allows_same_request_retry(client, app, monkeypatch):
    from test_workspace_runtime import visitor
    headers, conversation = visitor(client)
    original = __import__("workspace.api", fromlist=["respond"]).respond
    provider = Mock(side_effect=RuntimeError("private-provider-detail"))
    monkeypatch.setattr("workspace.api.respond", provider)
    body = {"message": "Explain SEO", "request_id": "retry-after-failure"}
    failed = client.post("/api/public/chat", json=body, headers=headers)
    assert failed.status_code == 503
    assert "private-provider-detail" not in failed.text
    assert app.state.db.get("systematic", "chat_lock", conversation) is None
    assert client.get("/api/public/conversation", headers=headers).json()["messages"] == []
    monkeypatch.setattr("workspace.api.respond", original)
    assert client.post("/api/public/chat", json=body, headers=headers).status_code == 200
