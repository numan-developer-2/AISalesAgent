from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from agents.models import AgentResult
from conversations.models import SalesConversation
from handover.service import HumanHandoverService
from leads.models import LeadProfile
from meetings.models import AvailableSlot
from meetings.service import MeetingBookingService
from proposals.service import ProposalRequestService

from .models import ToolResult
from .registry import ToolRegistry


@dataclass(frozen=True)
class ActionDecision:
    decision: str
    result: ToolResult | None = None
    reason: str | None = None


class SalesActionService:
    def __init__(self, meetings: MeetingBookingService, proposals: ProposalRequestService, handover: HumanHandoverService, registry: ToolRegistry | None = None) -> None:
        self.meetings = meetings
        self.proposals = proposals
        self.handover = handover
        self.registry = registry or ToolRegistry()

    def decide(self, agent_result: AgentResult, conversation: SalesConversation, lead: LeadProfile | None) -> ActionDecision:
        if not agent_result.requires_action or agent_result.action_intent == "none":
            return ActionDecision("no_action")
        action_type = self.registry.validate(agent_result.action_intent)
        if action_type == "book_meeting" and not (lead and lead.email):
            return ActionDecision("request_more_information", reason="valid email required before booking")
        if action_type == "request_proposal" and not (lead and (lead.email or lead.phone) and (lead.required_services or agent_result.recommended_services)):
            return ActionDecision("request_more_information", reason="lead contact and requested services required")
        if action_type == "human_handover":
            return ActionDecision("create_request")
        return ActionDecision("create_request")

    def check_meeting_availability(self, conversation_id: str, requested_date: date, daypart: str | None = None) -> ToolResult:
        self.registry.validate("check_meeting_availability")
        return self.meetings.check_availability(conversation_id, requested_date, daypart)

    def offer_booking_slot(self, conversation_id: str, lead: LeadProfile, slot: AvailableSlot, offered_slots: list[AvailableSlot]) -> ToolResult:
        self.registry.validate("book_meeting")
        return self.meetings.offer_booking_slot(conversation_id, lead, slot, offered_slots)

    def confirm_booking(self, action_reference: str, message: str, slot_id: str, lead: LeadProfile) -> ToolResult:
        self.registry.validate("book_meeting")
        return self.meetings.confirm_and_book(action_reference, message, slot_id, lead)

    def request_proposal(self, conversation_id: str, lead: LeadProfile, services: list[str]) -> ToolResult:
        self.registry.validate("request_proposal")
        return self.proposals.request(conversation_id, lead, services)

    def request_handover(self, conversation: SalesConversation, lead: LeadProfile | None, reason: str, priority: str = "normal") -> ToolResult:
        self.registry.validate("human_handover")
        return self.handover.request(conversation, lead, reason, priority)
