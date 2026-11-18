from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from llm.factory import create_llm_provider
from llm.models import LLMRequest
from llm.provider import (
    LLMProvider,
    LLMProviderError,
    LLMQuotaExceededError,
    LLMTransientUnavailableError,
)
from rag.service import RAGRetrievalService

from .context import format_history
from .models import (
    AgentError,
    AgentRequest,
    AgentResult,
    RAGUnavailableError,
    SALES_RESPONSE_SCHEMA,
    SourceMetadata,
    StructuredOutputError,
    parse_sales_response,
)
from .prompts import SALES_AGENT_SYSTEM_PROMPT
from .structured_knowledge import StructuredKnowledgeResolver


DEFAULT_RETRIEVAL_TOP_K = 5
DEFAULT_RETRIEVAL_THRESHOLD = 0.706


class SalesAgentService:
    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        rag_service: RAGRetrievalService | None = None,
        knowledge_resolver: StructuredKnowledgeResolver | None = None,
        retrieval_top_k: int = DEFAULT_RETRIEVAL_TOP_K,
        retrieval_threshold: float = DEFAULT_RETRIEVAL_THRESHOLD,
    ) -> None:
        self.llm_provider = llm_provider or create_llm_provider()
        self.rag_service = rag_service or RAGRetrievalService()
        self.knowledge_resolver = knowledge_resolver or StructuredKnowledgeResolver()
        self.retrieval_top_k = retrieval_top_k
        self.retrieval_threshold = retrieval_threshold

    def respond(self, request: AgentRequest) -> AgentResult:
        structured_context = self.knowledge_resolver.resolve(request.message)
        try:
            rag_result = self.rag_service.retrieve(
                request.message,
                match_count=self.retrieval_top_k,
                match_threshold=self.retrieval_threshold,
            )
        except Exception as exc:
            raise RAGUnavailableError("RAG retrieval unavailable") from exc
        user_prompt = self._build_user_prompt(
            request, structured_context, rag_result.context
        )
        llm_request = LLMRequest(
            system_prompt=SALES_AGENT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_schema=SALES_RESPONSE_SCHEMA,
        )
        try:
            llm_response = self.llm_provider.generate_structured(llm_request)
            parsed = parse_sales_response(llm_response.data)
        except (LLMQuotaExceededError, LLMTransientUnavailableError):
            raise
        except LLMProviderError as exc:
            raise AgentError("Sales response generation failed") from exc
        except StructuredOutputError:
            llm_response = self.llm_provider.generate_structured(llm_request)
            parsed = parse_sales_response(llm_response.data)

        grounding_status = self._derive_grounding_status(
            parsed.grounding_status, structured_context, rag_result.retrieved_count
        )
        grounding_sources = self._derive_grounding_sources(
            structured_context, rag_result.retrieved_count
        )
        sources = self._source_metadata(rag_result.chunks)
        answer = self._harden_pricing_wording(parsed.answer, structured_context)
        if grounding_status == "insufficient_context":
            answer = "I don't have enough approved information to confirm that. The sales team can verify the details."
            sources, grounding_sources = [], []
        return AgentResult(
            answer=answer,
            intent=parsed.intent,
            recommended_services=parsed.recommended_services,
            discovery_question=parsed.discovery_question,
            buying_signal=parsed.buying_signal,
            requires_action=parsed.requires_action,
            action_intent=parsed.action_intent if parsed.requires_action else "none",
            grounding_status=grounding_status,
            sources=sources,
            retrieved_count=rag_result.retrieved_count,
            grounding_sources=grounding_sources,
            lead_updates=parsed.lead_updates,
        )

    def _build_user_prompt(
        self,
        request: AgentRequest,
        structured_context: dict[str, Any],
        rag_context: str,
    ) -> str:
        return "\n\n".join(
            [
                "Conversation history:",
                format_history(request.history) or "none",
                "Visitor message:",
                request.message,
                "Optional request metadata:",
                json.dumps(
                    {
                        "conversation_id": request.conversation_id,
                        "language": request.language,
                        "source_page": request.source_page,
                    },
                    ensure_ascii=True,
                ),
                "Structured business context:",
                json.dumps(structured_context, ensure_ascii=True, indent=2),
                "Retrieved RAG context:",
                rag_context or "none",
                "Return a structured sales-agent response. Do not include sources; the application attaches sources.",
            ]
        )

    def _derive_grounding_status(
        self,
        model_status: str,
        structured_context: dict[str, Any],
        retrieved_count: int,
    ) -> str:
        if model_status == "insufficient_context":
            return "insufficient_context"
        has_structured = any(
            value
            for key, value in structured_context.items()
            if key != "internal_policy"
        )
        if retrieved_count > 0 or has_structured:
            return "grounded" if model_status == "grounded" else "partially_grounded"
        return "insufficient_context"

    def _derive_grounding_sources(
        self, structured_context: dict[str, Any], retrieved_count: int
    ) -> list[str]:
        sources = []
        has_structured = any(
            value
            for key, value in structured_context.items()
            if key != "internal_policy"
        )
        if retrieved_count > 0:
            sources.append("rag")
        if has_structured:
            sources.append("structured")
        return sources

    def _harden_pricing_wording(
        self, answer: str, structured_context: dict[str, Any]
    ) -> str:
        pricing = structured_context.get("pricing") or []
        hardened = answer
        for item in pricing:
            exact = item.get("exact_price_wording")
            plan = item.get("plan_name")
            price = item.get("price")
            currency = item.get("currency") or ""
            if not exact or not plan or price is None:
                continue
            try:
                value = Decimal(str(price))
                if not value.is_finite() or value < 0:
                    continue
            except InvalidOperation:
                continue
            amount = currency + format(value, ",.2f").removesuffix(".00")
            replacements = [
                f"The {plan} package starts at {amount} per month.",
                f"The {plan} package starts from {amount} per month.",
                f"The {plan} plan starts at {amount} per month.",
                f"The {plan} plan starts from {amount} per month.",
            ]
            for phrase in replacements:
                hardened = hardened.replace(phrase, exact)
        return hardened

    def _source_metadata(self, chunks: list[Any]) -> list[SourceMetadata]:
        seen: set[tuple[str | None, str | None]] = set()
        sources: list[SourceMetadata] = []
        for chunk in chunks:
            key = (chunk.title, chunk.source_url)
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                SourceMetadata(
                    title=chunk.title,
                    source_url=chunk.source_url,
                    content_type=chunk.content_type,
                    similarity=chunk.similarity,
                )
            )
        return sources
