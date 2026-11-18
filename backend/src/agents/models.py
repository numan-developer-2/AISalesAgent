from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


Intent = Literal[
    "general_information",
    "service_discovery",
    "service_recommendation",
    "pricing",
    "company_information",
    "objection_handling",
    "booking_interest",
    "proposal_interest",
    "human_handover",
    "support_request",
    "out_of_scope",
]
BuyingSignal = Literal["none", "low", "medium", "high"]
ActionIntent = Literal["book_meeting", "request_proposal", "human_handover", "none"]
GroundingStatus = Literal["grounded", "partially_grounded", "insufficient_context"]

MAX_MESSAGE_LENGTH = 2000
MAX_HISTORY_ITEMS = 10


class AgentError(RuntimeError):
    pass


class InvalidAgentRequest(AgentError):
    pass


class AgentConfigurationError(AgentError):
    pass


class StructuredOutputError(AgentError):
    pass


class RAGUnavailableError(AgentError):
    pass


@dataclass(frozen=True)
class ConversationMessage:
    role: Literal["user", "assistant"]
    content: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ConversationMessage":
        role = value.get("role")
        content = value.get("content")
        if role not in ("user", "assistant"):
            raise InvalidAgentRequest("history role must be user or assistant")
        if not isinstance(content, str) or not content.strip():
            raise InvalidAgentRequest("history content must be non-empty text")
        return cls(role=role, content=content.strip())


@dataclass(frozen=True)
class AgentRequest:
    message: str
    conversation_id: str | None = None
    history: list[ConversationMessage] = field(default_factory=list)
    language: str | None = None
    source_page: str | None = None

    @classmethod
    def create(
        cls,
        message: object,
        conversation_id: str | None = None,
        history: list[dict[str, Any] | ConversationMessage] | None = None,
        language: str | None = None,
        source_page: str | None = None,
    ) -> "AgentRequest":
        if not isinstance(message, str):
            raise InvalidAgentRequest("message must be text")
        normalized = message.strip()
        if not normalized:
            raise InvalidAgentRequest("message must not be empty")
        if len(normalized) > MAX_MESSAGE_LENGTH:
            raise InvalidAgentRequest(
                f"message must be {MAX_MESSAGE_LENGTH} characters or fewer"
            )
        clean_history: list[ConversationMessage] = []
        for item in history or []:
            clean_history.append(
                item
                if isinstance(item, ConversationMessage)
                else ConversationMessage.from_dict(item)
            )
        return cls(
            message=normalized,
            conversation_id=conversation_id,
            history=clean_history[-MAX_HISTORY_ITEMS:],
            language=language,
            source_page=source_page,
        )


@dataclass(frozen=True)
class SourceMetadata:
    title: str | None
    source_url: str | None
    content_type: str | None
    similarity: float


@dataclass(frozen=True)
class SalesAgentResponse:
    answer: str
    intent: Intent
    recommended_services: list[str]
    discovery_question: str | None
    buying_signal: BuyingSignal
    requires_action: bool
    action_intent: ActionIntent
    grounding_status: GroundingStatus
    grounding_sources: list[str]
    lead_updates: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentResult:
    answer: str
    intent: Intent
    recommended_services: list[str]
    discovery_question: str | None
    buying_signal: BuyingSignal
    requires_action: bool
    action_intent: ActionIntent
    grounding_status: GroundingStatus
    sources: list[SourceMetadata]
    retrieved_count: int
    grounding_sources: list[str]
    lead_updates: dict[str, Any] = field(default_factory=dict)


SALES_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "answer": {"type": "STRING"},
        "intent": {
            "type": "STRING",
            "enum": [
                "general_information",
                "service_discovery",
                "service_recommendation",
                "pricing",
                "company_information",
                "objection_handling",
                "booking_interest",
                "proposal_interest",
                "human_handover",
                "support_request",
                "out_of_scope",
            ],
        },
        "recommended_services": {"type": "ARRAY", "items": {"type": "STRING"}},
        "discovery_question": {"type": "STRING", "nullable": True},
        "buying_signal": {"type": "STRING", "enum": ["none", "low", "medium", "high"]},
        "requires_action": {"type": "BOOLEAN"},
        "action_intent": {
            "type": "STRING",
            "enum": ["book_meeting", "request_proposal", "human_handover", "none"],
        },
        "grounding_status": {
            "type": "STRING",
            "enum": ["grounded", "partially_grounded", "insufficient_context"],
        },
        "lead_updates": {
            "type": "OBJECT",
            "nullable": True,
            "properties": {
                "full_name": {"type": "STRING", "nullable": True},
                "company_name": {"type": "STRING", "nullable": True},
                "email": {"type": "STRING", "nullable": True},
                "phone": {"type": "STRING", "nullable": True},
                "website_url": {"type": "STRING", "nullable": True},
                "industry": {"type": "STRING", "nullable": True},
                "required_services": {"type": "ARRAY", "items": {"type": "STRING"}},
                "business_goal": {"type": "STRING", "nullable": True},
                "budget_range": {"type": "STRING", "nullable": True},
                "timeline": {"type": "STRING", "nullable": True},
                "authority_status": {"type": "STRING", "nullable": True},
            },
        },
    },
    "required": [
        "answer",
        "intent",
        "recommended_services",
        "discovery_question",
        "buying_signal",
        "requires_action",
        "action_intent",
        "grounding_status",
    ],
}


def parse_sales_response(data: dict[str, Any]) -> SalesAgentResponse:
    if not isinstance(data, dict):
        raise StructuredOutputError("structured response must be an object")
    for key in SALES_RESPONSE_SCHEMA["required"]:
        if key not in data:
            raise StructuredOutputError(f"missing structured response field: {key}")
    if (
        not isinstance(data["answer"], str)
        or not 1 <= len(data["answer"].strip()) <= 6000
    ):
        raise StructuredOutputError(
            "answer must be non-empty text of at most 6000 characters"
        )
    for key in ("intent", "buying_signal", "action_intent", "grounding_status"):
        if data[key] not in SALES_RESPONSE_SCHEMA["properties"][key]["enum"]:
            raise StructuredOutputError(f"invalid {key}")
    if type(data["requires_action"]) is not bool:
        raise StructuredOutputError("requires_action must be a boolean")
    if not isinstance(data["recommended_services"], list) or any(
        not isinstance(v, str) for v in data["recommended_services"]
    ):
        raise StructuredOutputError("recommended_services must be a list of text")
    if data["discovery_question"] is not None and not isinstance(
        data["discovery_question"], str
    ):
        raise StructuredOutputError("discovery_question must be text or null")
    updates = data.get("lead_updates")
    if updates is not None and not isinstance(updates, dict):
        raise StructuredOutputError("lead_updates must be an object")
    try:
        response = SalesAgentResponse(
            answer=str(data["answer"]).strip(),
            intent=data["intent"],
            recommended_services=[
                str(item) for item in data.get("recommended_services", [])
            ][:3],
            discovery_question=data.get("discovery_question"),
            buying_signal=data["buying_signal"],
            requires_action=bool(data["requires_action"]),
            action_intent=data.get("action_intent") or "none",
            grounding_status=data["grounding_status"],
            grounding_sources=[],
            lead_updates=data.get("lead_updates") or {},
        )
    except KeyError as exc:
        raise StructuredOutputError(
            f"missing structured response field: {exc.args[0]}"
        ) from exc
    if not response.answer:
        raise StructuredOutputError("structured response answer is empty")
    return response
