from __future__ import annotations

from .context_builder import RAGContextBuilder
from .models import RetrievalRequest, RetrievalResult
from .query_embedding import GeminiQueryEmbedder
from .retriever import SupabaseRAGRetriever


class RAGRetrievalService:
    def __init__(
        self,
        embedder: GeminiQueryEmbedder | None = None,
        retriever: SupabaseRAGRetriever | None = None,
        context_builder: RAGContextBuilder | None = None,
    ) -> None:
        self.embedder = embedder or GeminiQueryEmbedder()
        self.retriever = retriever or SupabaseRAGRetriever()
        self.context_builder = context_builder or RAGContextBuilder()

    def retrieve(
        self,
        query: str,
        match_count: int = 5,
        match_threshold: float = 0.50,
        content_type: str | None = None,
    ) -> RetrievalResult:
        request = RetrievalRequest(
            query=query,
            match_count=match_count,
            match_threshold=match_threshold,
            content_type=content_type,
        )
        embedding = self.embedder.embed_query(request.query)
        chunks = self.retriever.retrieve(request, embedding)
        context = self.context_builder.build(chunks)
        return RetrievalResult(query=request.query, chunks=chunks, context=context)
