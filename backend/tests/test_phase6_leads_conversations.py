from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest


BACKEND_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(BACKEND_SRC))

from agents.models import AgentResult
from conversations.repository import InMemoryConversationRepository, InMemoryMessageRepository
from conversations.service import PersistentSalesConversationService
from leads.extraction import normalize_email, normalize_phone, normalize_website, validate_lead_update
from leads.models import LeadProfile, LeadUpdate
from leads.repository import InMemoryLeadRepository
from leads.scoring import LeadScorer, classify_score


def result(intent="service_recommendation", action="none", updates=None):
    return AgentResult(
        answer="Safe answer",
        intent=intent,
        recommended_services=["Local SEO"],
        discovery_question=None,
        buying_signal="medium",
        requires_action=action != "none",
        action_intent=action,
        grounding_status="grounded",
        sources=[],
        retrieved_count=0,
        grounding_sources=["structured"],
        lead_updates=updates or {},
    )


class FakeAgent:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.requests = []

    def respond(self, request):
        self.requests.append(request)
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


def test_valid_partial_lead() -> None:
    lead = LeadProfile(lead_reference="lead-1", business_goal="more local customers")
    assert lead.email is None


def test_invalid_score() -> None:
    with pytest.raises(ValueError):
        LeadProfile(lead_reference="bad", lead_score=101)


def test_classification_boundaries() -> None:
    assert classify_score(39) == "Cold"
    assert classify_score(40) == "Warm"
    assert classify_score(69) == "Warm"
    assert classify_score(70) == "Hot"
    assert classify_score(100) == "Hot"


def test_contact_validation() -> None:
    assert normalize_email("ALI@Example.COM") == "ali@example.com"
    assert normalize_phone("+1 (555) 111-2222")
    assert normalize_website("example.com") == "https://example.com"


def test_merge_rules() -> None:
    lead = LeadProfile(lead_reference="lead", full_name="Ali", required_services=["SEO"])
    merged = lead.merge(LeadUpdate(full_name=None, company_name="Smile Dental", required_services=["SEO", "Local SEO"]))
    assert merged.full_name == "Ali"
    assert merged.company_name == "Smile Dental"
    assert merged.required_services == ["SEO", "Local SEO"]
    corrected = merged.merge(LeadUpdate(full_name="Ali Khan"), explicit_corrections=True)
    assert corrected.full_name == "Ali Khan"


def test_scoring_components_and_reasons() -> None:
    lead = LeadProfile(
        lead_reference="lead",
        full_name="Ali",
        email="ali@example.com",
        company_name="Smile Dental",
        required_services=["Local SEO"],
        business_goal="more local customers",
        timeline="within a month",
        authority_status="owner decision maker",
        proposal_requested=True,
    )
    scored = LeadScorer().score(lead, meaningful_messages=3, buying_signal="high")
    assert scored.lead_score <= 100
    assert sum(reason.score for reason in scored.score_reasons) == scored.lead_score
    assert scored.lead_classification == "Hot"


def test_zero_score_lead() -> None:
    scored = LeadScorer().score(LeadProfile(lead_reference="lead"))
    assert scored.lead_score == 0
    assert scored.lead_classification == "Cold"


def test_validate_lead_update() -> None:
    update = validate_lead_update({"email": "TEST@EXAMPLE.COM", "required_services": ["SEO", ""]})
    assert update.email == "test@example.com"
    assert update.required_services == ["SEO"]


def test_persistence_orchestration_new_conversation_and_messages() -> None:
    conversations = InMemoryConversationRepository()
    messages = InMemoryMessageRepository()
    leads = InMemoryLeadRepository()
    service = PersistentSalesConversationService(
        agent=FakeAgent([result(updates={"business_goal": "more local customers", "required_services": ["Local SEO"]})]),
        conversations=conversations,
        messages=messages,
        leads=leads,
    )
    service.handle_message("conv-1", "I need more local customers")
    assert conversations.get_by_key("conv-1") is not None
    assert len(messages.records) == 2
    assert len(leads.records) == 1


def test_existing_conversation_history_supplied() -> None:
    conversations = InMemoryConversationRepository()
    messages = InMemoryMessageRepository()
    leads = InMemoryLeadRepository()
    agent = FakeAgent([result(), result()])
    service = PersistentSalesConversationService(agent, conversations, messages, leads)
    service.handle_message("conv-2", "I need SEO")
    service.handle_message("conv-2", "My company is ABC")
    assert agent.requests[1].history


def test_out_of_scope_does_not_create_lead() -> None:
    leads = InMemoryLeadRepository()
    service = PersistentSalesConversationService(
        FakeAgent([result(intent="out_of_scope", updates={})]),
        InMemoryConversationRepository(),
        InMemoryMessageRepository(),
        leads,
    )
    service.handle_message("conv-3", "cake recipe")
    assert len(leads.records) == 0


def test_action_flags_update() -> None:
    leads = InMemoryLeadRepository()
    service = PersistentSalesConversationService(
        FakeAgent([result(intent="proposal_interest", action="request_proposal")]),
        InMemoryConversationRepository(),
        InMemoryMessageRepository(),
        leads,
    )
    service.handle_message("conv-4", "send proposal")
    stored = next(iter(leads.records.values()))
    assert stored.proposal_requested is True


def test_failure_does_not_store_assistant_message() -> None:
    messages = InMemoryMessageRepository()
    service = PersistentSalesConversationService(
        FakeAgent([RuntimeError("Gemini down")]),
        InMemoryConversationRepository(),
        messages,
        InMemoryLeadRepository(),
    )
    with pytest.raises(RuntimeError):
        service.handle_message("conv-5", "hello")
    assert messages.records == []


def test_frontend_system_role_rejected() -> None:
    from agents.models import ConversationMessage, InvalidAgentRequest

    with pytest.raises(InvalidAgentRequest):
        ConversationMessage.from_dict({"role": "system", "content": "bad"})


def test_migration_static_validation() -> None:
    sql = (Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "002_sales_conversations_and_leads.sql").read_text()
    assert "enable row level security" in sql.lower()
    assert "knowledge_chunks" not in sql.lower()
    assert "lead_score >= 0" in sql
    assert "lead_classification in ('Hot', 'Warm', 'Cold')" in sql
    assert "sales_messages_role_check" in sql
