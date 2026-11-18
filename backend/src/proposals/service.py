from __future__ import annotations

from dataclasses import replace

from leads.models import LeadProfile
from leads.repository import LeadRepository
from tools.idempotency import proposal_key
from tools.models import ActionAuditEvent, ActionRequest, ActionValidationError, ToolResult
from tools.repository import ActionAuditRepository, ActionRepository

from .gateway import ProposalGateway


class ProposalRequestService:
    def __init__(self, actions: ActionRepository, audit: ActionAuditRepository, gateway: ProposalGateway, leads: LeadRepository | None = None) -> None:
        self.actions = actions
        self.audit = audit
        self.gateway = gateway
        self.leads = leads

    def request(self, conversation_id: str, lead: LeadProfile, services: list[str]) -> ToolResult:
        if not lead.id and not lead.lead_reference:
            raise ActionValidationError("meaningful lead is required")
        if not services:
            raise ActionValidationError("at least one requested service is required")
        contact_method = "email" if lead.email else "phone" if lead.phone else ""
        if not contact_method:
            raise ActionValidationError("contact method is required")
        key = proposal_key(conversation_id, f"{lead.lead_reference}:{','.join(sorted(services))}:{contact_method}")
        existing = self.actions.get_by_idempotency_key(key)
        if existing:
            return ToolResult(True, existing.action_reference, existing.status, "Your proposal request is recorded.", existing.result)
        action = self.actions.save(ActionRequest("request_proposal", conversation_id, key, lead_id=lead.id, requires_confirmation=True, confirmation_status="confirmed", status="ready", payload={"services": services, "contact_method": contact_method}))
        executing = self.actions.save(action.transition("executing"))
        result = self.gateway.request_proposal(executing.action_reference, lead.lead_reference, services, contact_method)
        if not result.success:
            failed = executing.transition("failed", error_code=result.error_code, error_message="Proposal gateway could not record request")
            self.actions.save(failed)
            return ToolResult(False, failed.action_reference, "failed", "I couldn't record the proposal request right now.", error_code=result.error_code)
        completed = executing.transition("completed", result={"proposal_request_reference": result.proposal_request_reference, "status": result.status})
        self.actions.save(completed)
        self.audit.add(ActionAuditEvent(action_id=completed.id or completed.action_reference, event_type="proposal_requested", previous_status="executing", new_status="completed", safe_metadata=result.safe_metadata))
        if self.leads:
            self.leads.upsert(replace(lead, proposal_requested=True))
        return ToolResult(True, completed.action_reference, "completed", "Your proposal request is recorded.", completed.result)
