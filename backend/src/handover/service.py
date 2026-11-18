from __future__ import annotations

from dataclasses import replace

from conversations.models import SalesConversation
from conversations.repository import ConversationRepository
from leads.models import LeadProfile
from leads.repository import LeadRepository
from tools.idempotency import handover_key
from tools.models import ActionAuditEvent, ActionRequest, ActionValidationError, ToolResult
from tools.repository import ActionAuditRepository, ActionRepository

from .gateway import HandoverGateway


class HumanHandoverService:
    def __init__(self, actions: ActionRepository, audit: ActionAuditRepository, gateway: HandoverGateway, conversations: ConversationRepository | None = None, leads: LeadRepository | None = None) -> None:
        self.actions = actions
        self.audit = audit
        self.gateway = gateway
        self.conversations = conversations
        self.leads = leads

    def request(self, conversation: SalesConversation, lead: LeadProfile | None, reason: str, priority: str = "normal") -> ToolResult:
        priority = self._priority(priority, lead)
        key = handover_key(conversation.id or conversation.conversation_key, f"{reason}:{priority}")
        existing = self.actions.get_by_idempotency_key(key)
        if existing:
            return ToolResult(True, existing.action_reference, existing.status, "I've flagged this for a human representative.", existing.result)
        action = self.actions.save(ActionRequest("human_handover", conversation.id or conversation.conversation_key, key, lead_id=lead.id if lead else None, requires_confirmation=True, confirmation_status="confirmed", status="ready", payload={"reason": reason[:200], "priority": priority}))
        executing = self.actions.save(action.transition("executing"))
        result = self.gateway.request_handover(executing.action_reference, executing.conversation_id, reason[:200], priority)
        if not result.success:
            failed = executing.transition("failed", error_code=result.error_code, error_message="Handover gateway could not record request")
            self.actions.save(failed)
            return ToolResult(False, failed.action_reference, "failed", "I couldn't request human handover right now.", error_code=result.error_code)
        completed = executing.transition("completed", result={"handover_reference": result.handover_reference, "status": result.status, "priority": priority})
        self.actions.save(completed)
        if self.conversations:
            self.conversations.upsert(replace(conversation, status="handover_requested"))
        if self.leads and lead:
            self.leads.upsert(replace(lead, human_handover_requested=True))
        self.audit.add(ActionAuditEvent(action_id=completed.id or completed.action_reference, event_type="handover_requested", previous_status="executing", new_status="completed", safe_metadata={"priority": priority}))
        return ToolResult(True, completed.action_reference, "completed", "I've flagged this for a human representative.", completed.result)

    def _priority(self, requested: str, lead: LeadProfile | None) -> str:
        if requested not in {"normal", "high", "urgent"}:
            raise ActionValidationError("invalid handover priority")
        if requested == "urgent":
            return "urgent"
        if lead and lead.lead_classification == "Hot":
            return "high"
        return requested
