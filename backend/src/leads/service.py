from __future__ import annotations

from dataclasses import replace

from agents.models import AgentResult

from .extraction import validate_lead_update
from .models import LeadProfile
from .scoring import LeadScorer


SALES_INTENTS = {
    "service_discovery", "service_recommendation", "pricing", "booking_interest",
    "proposal_interest", "human_handover", "objection_handling",
}


class LeadService:
    def __init__(self, scorer: LeadScorer | None = None) -> None:
        self.scorer = scorer or LeadScorer()

    def should_create_lead(self, result: AgentResult, update: dict) -> bool:
        return (
            result.intent in SALES_INTENTS
            or bool(update.get("email") or update.get("phone"))
            or bool(update.get("business_goal") or update.get("required_services"))
        )

    def apply_agent_result(
        self,
        lead: LeadProfile,
        result: AgentResult,
        lead_updates: dict,
        meaningful_messages: int,
    ) -> LeadProfile:
        update = validate_lead_update(lead_updates)
        merged = lead.merge(update)
        merged = replace(
            merged,
            meeting_requested=lead.meeting_requested or result.action_intent == "book_meeting",
            proposal_requested=lead.proposal_requested or result.action_intent == "request_proposal",
            human_handover_requested=lead.human_handover_requested or result.action_intent == "human_handover",
        )
        return self.scorer.score(merged, meaningful_messages=meaningful_messages, buying_signal=result.buying_signal)
