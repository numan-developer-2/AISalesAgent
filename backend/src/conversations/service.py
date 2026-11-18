from __future__ import annotations

from dataclasses import replace

from agents.models import AgentRequest, AgentResult
from agents.service import SalesAgentService
from leads.models import LeadProfile
from leads.repository import LeadRepository
from leads.service import LeadService

from .memory import bounded_history
from .models import SalesConversation, SalesMessage
from .repository import ConversationRepository, MessageRepository


class PersistentSalesConversationService:
    def __init__(
        self,
        agent: SalesAgentService,
        conversations: ConversationRepository,
        messages: MessageRepository,
        leads: LeadRepository,
        lead_service: LeadService | None = None,
    ) -> None:
        self.agent = agent
        self.conversations = conversations
        self.messages = messages
        self.leads = leads
        self.lead_service = lead_service or LeadService()

    def handle_message(
        self,
        conversation_key: str,
        message: str,
        language: str | None = None,
        source_page: str | None = None,
    ) -> AgentResult:
        if not conversation_key or not conversation_key.strip():
            raise ValueError("conversation_key is required")
        conversation = self.conversations.get_by_key(conversation_key) or self.conversations.upsert(
            SalesConversation(conversation_key=conversation_key, language=language, source_page=source_page)
        )
        history = bounded_history(self.messages.list_recent(conversation.id or conversation_key, 10))
        result = self.agent.respond(
            AgentRequest.create(message, conversation_id=conversation_key, history=history, language=language, source_page=source_page)
        )
        lead = self._resolve_lead(conversation, result)
        if lead:
            updated = self.lead_service.apply_agent_result(
                lead,
                result,
                result.lead_updates,
                meaningful_messages=len(history) + 1,
            )
            stored = self.leads.upsert(updated)
            conversation = self.conversations.upsert(replace(conversation, lead_id=stored.id))
        conversation_id = conversation.id or conversation_key
        self.messages.add(SalesMessage(conversation_id=conversation_id, role="user", content=message))
        self.messages.add(
            SalesMessage(
                conversation_id=conversation_id,
                role="assistant",
                content=result.answer,
                intent=result.intent,
                grounding_status=result.grounding_status,
                grounding_sources=result.grounding_sources,
                recommended_services=result.recommended_services,
                requires_action=result.requires_action,
                action_intent=result.action_intent,
                source_metadata=result.sources,
            )
        )
        return result

    def _resolve_lead(self, conversation: SalesConversation, result: AgentResult) -> LeadProfile | None:
        if conversation.lead_id:
            existing = self.leads.get_by_id(conversation.lead_id)
            if existing:
                return existing
        if not self.lead_service.should_create_lead(result, result.lead_updates):
            return None
        return LeadProfile(lead_reference=f"lead-{conversation.conversation_key}", source_page=conversation.source_page, language=conversation.language)
