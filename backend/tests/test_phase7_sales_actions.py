from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest


BACKEND_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(BACKEND_SRC))

from agents.models import AgentResult
from conversations.models import SalesConversation
from conversations.repository import InMemoryConversationRepository
from handover.gateway import MockHandoverGateway
from handover.service import HumanHandoverService
from leads.models import LeadProfile
from leads.repository import InMemoryLeadRepository
from meetings.availability import MeetingScheduleConfig, generate_slots
from meetings.gateway import MockCalendarGateway
from meetings.models import AvailabilityRequest
from meetings.service import MeetingBookingService
from proposals.gateway import MockProposalGateway
from proposals.service import ProposalRequestService
from tools.confirmation import ConfirmationGuard, looks_explicit_confirmation
from tools.models import ActionRequest, ActionValidationError, ConfirmationError, InvalidActionTransition, UnknownActionError
from tools.registry import ToolRegistry
from tools.repository import InMemoryActionAuditRepository, InMemoryActionRepository
from tools.service import SalesActionService


def _result(action="none") -> AgentResult:
    return AgentResult(
        answer="ok",
        intent="booking_interest" if action == "book_meeting" else "service_recommendation",
        recommended_services=["SEO"],
        discovery_question=None,
        buying_signal="medium",
        requires_action=action != "none",
        action_intent=action,
        grounding_status="grounded",
        sources=[],
        retrieved_count=0,
        grounding_sources=[],
        lead_updates={},
    )


def _stack(fail_booking=False):
    actions = InMemoryActionRepository()
    audit = InMemoryActionAuditRepository()
    leads = InMemoryLeadRepository()
    conversations = InMemoryConversationRepository()
    config = MeetingScheduleConfig(timezone="Asia/Karachi")
    calendar = MockCalendarGateway(config=config, fail_booking=fail_booking)
    service = SalesActionService(
        MeetingBookingService(actions, audit, calendar, config),
        ProposalRequestService(actions, audit, MockProposalGateway(), leads),
        HumanHandoverService(actions, audit, MockHandoverGateway(), conversations, leads),
    )
    return service, actions, audit, leads, conversations, calendar


def test_registry_rejects_unknown_tool() -> None:
    with pytest.raises(UnknownActionError):
        ToolRegistry().validate("delete_everything")


def test_action_state_machine_blocks_invalid_jump() -> None:
    action = ActionRequest("book_meeting", "conv", "booking:1", requires_confirmation=True)
    with pytest.raises(InvalidActionTransition):
        action.transition("completed")


def test_confirmation_language_is_deterministic() -> None:
    assert looks_explicit_confirmation("Yes, book Tuesday at 2 PM")
    assert not looks_explicit_confirmation("Tuesday might work")
    assert not looks_explicit_confirmation("What times are available?")


def test_confirmation_requires_current_slot_and_state() -> None:
    action = ActionRequest(
        "book_meeting",
        "conv",
        "booking:slot",
        status="awaiting_confirmation",
        requires_confirmation=True,
        payload={"selected_slot_id": "slot-1", "offered_slot_ids": ["slot-1"]},
    )
    confirmed = ConfirmationGuard().confirm_slot(action, "Confirm that slot", "slot-1")
    assert confirmed.status == "ready"
    with pytest.raises(ConfirmationError):
        ConfirmationGuard().confirm_slot(action, "Confirm that slot", "slot-2")


def test_expired_action_cannot_confirm() -> None:
    now = datetime.now(tz=ZoneInfo("UTC"))
    action = ActionRequest(
        "book_meeting",
        "conv",
        "booking:expired",
        status="awaiting_confirmation",
        requires_confirmation=True,
        payload={"selected_slot_id": "slot-1", "offered_slot_ids": ["slot-1"]},
        expires_at=now - timedelta(minutes=1),
    )
    expired = ConfirmationGuard().confirm_slot(action, "Confirm that slot", "slot-1", now=now)
    assert expired.status == "expired"


def test_availability_working_hours_busy_overlap_buffer_and_boundary() -> None:
    tz = ZoneInfo("Asia/Karachi")
    config = MeetingScheduleConfig(timezone="Asia/Karachi", workday_start="10:00", workday_end="12:00", duration_minutes=30, buffer_minutes=15)
    busy = [
        (datetime(2026, 8, 18, 10, 0, tzinfo=tz), datetime(2026, 8, 18, 10, 30, tzinfo=tz)),
        (datetime(2026, 8, 18, 10, 20, tzinfo=tz), datetime(2026, 8, 18, 10, 45, tzinfo=tz)),
    ]
    slots = generate_slots(date(2026, 8, 18), busy, config)
    assert all(slot.start_at.tzinfo is not None for slot in slots)
    assert all(slot.end_at.hour <= 12 for slot in slots)
    assert slots and slots[0].start_at.hour == 11
    assert generate_slots(date(2026, 8, 22), [], config) == []


def test_booking_requires_email_and_offered_slot() -> None:
    service, *_rest, calendar = _stack()
    lead = LeadProfile(lead_reference="lead")
    slots = calendar.get_availability(AvailabilityRequest("conv", date(2026, 8, 18))).slots
    with pytest.raises(ActionValidationError):
        service.offer_booking_slot("conv", lead, slots[0], slots)


def test_booking_requires_confirmation_then_mock_success_and_duplicate_is_idempotent() -> None:
    service, actions, _audit, _leads, _conversations, calendar = _stack()
    lead = LeadProfile(id="lead-id", lead_reference="lead", email="qa@example.com", full_name="QA")
    slots = calendar.get_availability(AvailabilityRequest("conv", date(2026, 8, 18))).slots
    offer = service.offer_booking_slot("conv", lead, slots[0], slots)
    assert offer.status == "awaiting_confirmation"
    with pytest.raises(ConfirmationError):
        service.confirm_booking(offer.action_reference, "Tuesday might work", slots[0].slot_id, lead)
    booked = service.confirm_booking(offer.action_reference, "Yes, book it", slots[0].slot_id, lead)
    duplicate = service.confirm_booking(offer.action_reference, "Yes, book it", slots[0].slot_id, lead)
    assert booked.status == "completed"
    assert duplicate.action_reference == booked.action_reference
    assert len(calendar.created) == 1
    assert len(actions.records) == 1


def test_booking_provider_failure_is_safe() -> None:
    service, *_rest, calendar = _stack(fail_booking=True)
    lead = LeadProfile(id="lead-id", lead_reference="lead", email="qa@example.com")
    slots = calendar.get_availability(AvailabilityRequest("conv", date(2026, 8, 18))).slots
    offer = service.offer_booking_slot("conv", lead, slots[0], slots)
    failed = service.confirm_booking(offer.action_reference, "Confirm that slot", slots[0].slot_id, lead)
    assert failed.success is False
    assert "couldn't complete" in failed.customer_message


def test_proposal_requires_contact_service_and_is_idempotent() -> None:
    service, actions, _audit, _leads, *_ = _stack()
    lead = LeadProfile(id="lead-id", lead_reference="lead", email="qa@example.com")
    with pytest.raises(ActionValidationError):
        service.request_proposal("conv", lead, [])
    one = service.request_proposal("conv", lead, ["SEO"])
    two = service.request_proposal("conv", lead, ["SEO"])
    assert one.action_reference == two.action_reference
    assert len(actions.records) == 1


def test_handover_updates_conversation_priority_and_is_idempotent() -> None:
    service, actions, _audit, _leads, conversations, *_ = _stack()
    conversation = conversations.upsert(SalesConversation(conversation_key="conv"))
    lead = LeadProfile(id="lead-id", lead_reference="lead", lead_score=80, lead_classification="Hot")
    one = service.request_handover(conversation, lead, "Need human")
    two = service.request_handover(conversation, lead, "Need human")
    assert one.action_reference == two.action_reference
    assert one.data["priority"] == "high"
    assert conversations.get_by_key("conv").status == "handover_requested"
    assert len(actions.records) == 1


def test_action_decision_requests_more_info_for_booking_without_email() -> None:
    service, *_ = _stack()
    decision = service.decide(_result("book_meeting"), SalesConversation("conv"), LeadProfile(lead_reference="lead"))
    assert decision.decision == "request_more_information"


def test_hidden_and_provider_secrets_are_not_persisted() -> None:
    action = ActionRequest("human_handover", "conv", "handover:1", payload={"api_key": "secret", "safe": "ok", "raw_rag_context": "hidden"})
    assert action.payload == {"safe": "ok"}
