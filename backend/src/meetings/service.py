from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from leads.models import LeadProfile
from tools.confirmation import ConfirmationGuard
from tools.idempotency import booking_key, stable_idempotency_key
from tools.models import ActionAuditEvent, ActionRequest, ActionValidationError, ToolResult, utc_now
from tools.repository import ActionAuditRepository, ActionRepository

from .availability import MeetingScheduleConfig
from .gateway import CalendarGateway
from .models import AvailabilityRequest, AvailableSlot, BookingRequest


class MeetingBookingService:
    def __init__(self, actions: ActionRepository, audit: ActionAuditRepository, calendar: CalendarGateway, config: MeetingScheduleConfig | None = None) -> None:
        self.actions = actions
        self.audit = audit
        self.calendar = calendar
        self.config = config or MeetingScheduleConfig.from_env()
        self.confirmation = ConfirmationGuard()

    def check_availability(self, conversation_id: str, requested_date: date, daypart: str | None = None) -> ToolResult:
        key = stable_idempotency_key("availability", conversation_id, requested_date.isoformat(), daypart)
        existing = self.actions.get_by_idempotency_key(key)
        if existing:
            return ToolResult(True, existing.action_reference, existing.status, "I found available times.", existing.result)
        action = self.actions.save(ActionRequest("check_meeting_availability", conversation_id, key, requires_confirmation=False, payload={"requested_date": requested_date.isoformat(), "daypart": daypart}))
        result = self.calendar.get_availability(AvailabilityRequest(conversation_id, requested_date, self.config.timezone, daypart))
        data = {"slots": [_slot_to_dict(slot) for slot in result.slots]}
        completed = action.transition("executing").transition("completed", result=data)
        self.actions.save(completed)
        self.audit.add(ActionAuditEvent(action_id=completed.id or completed.action_reference, event_type="availability_checked", previous_status="requested", new_status="completed", safe_metadata={"slot_count": len(result.slots)}))
        return ToolResult(True, completed.action_reference, "completed", "I found available times.", data)

    def offer_booking_slot(self, conversation_id: str, lead: LeadProfile, slot: AvailableSlot, offered_slots: list[AvailableSlot]) -> ToolResult:
        if not lead.email:
            raise ActionValidationError("valid lead email is required before booking")
        key = booking_key(conversation_id, slot.slot_id)
        existing = self.actions.get_by_idempotency_key(key)
        if existing:
            return ToolResult(True, existing.action_reference, existing.status, "Please confirm the selected slot.", existing.payload)
        action = ActionRequest(
            "book_meeting",
            conversation_id,
            key,
            lead_id=lead.id,
            requires_confirmation=True,
            status="awaiting_confirmation",
            payload={"selected_slot_id": slot.slot_id, "offered_slot_ids": [s.slot_id for s in offered_slots], "slot": _slot_to_dict(slot), "lead_email": lead.email, "lead_name": lead.full_name},
            expires_at=utc_now() + timedelta(minutes=30),
        )
        stored = self.actions.save(action)
        self.audit.add(ActionAuditEvent(action_id=stored.id or stored.action_reference, event_type="booking_slot_offered", new_status="awaiting_confirmation", safe_metadata={"slot_id": slot.slot_id}))
        return ToolResult(True, stored.action_reference, "awaiting_confirmation", "Please confirm the selected slot.", stored.payload)

    def confirm_and_book(self, action_reference: str, message: str, slot_id: str, lead: LeadProfile) -> ToolResult:
        action = self.actions.get_by_reference(action_reference)
        if not action:
            raise ActionValidationError("booking action not found")
        if action.status == "completed":
            return ToolResult(True, action.action_reference, "completed", "Your meeting has been booked.", action.result)
        if not lead.email:
            raise ActionValidationError("valid lead email is required before booking")
        ready = self.actions.save(self.confirmation.confirm_slot(action, message, slot_id))
        if ready.status == "expired":
            return ToolResult(False, ready.action_reference, "expired", "This booking offer has expired. Please choose a new time.", error_code="booking_offer_expired")
        slot = _slot_from_dict(ready.payload["slot"])
        executing = self.actions.save(ready.transition("executing"))
        booking = self.calendar.create_meeting(BookingRequest(executing.action_reference, executing.conversation_id, executing.lead_id, lead.email, lead.full_name, slot))
        if not booking.success:
            failed = executing.transition("failed", error_code=booking.error_code, error_message="Calendar gateway could not complete booking")
            self.actions.save(failed)
            self.audit.add(ActionAuditEvent(action_id=failed.id or failed.action_reference, event_type="booking_failed", previous_status="executing", new_status="failed", safe_metadata={"error_code": booking.error_code}))
            return ToolResult(False, failed.action_reference, "failed", "I couldn't complete the booking right now.", error_code=booking.error_code)
        completed = executing.transition("completed", result={"external_event_id": booking.external_event_id, "external_event_url": booking.external_event_url, "slot_id": slot.slot_id})
        self.actions.save(completed)
        self.audit.add(ActionAuditEvent(action_id=completed.id or completed.action_reference, event_type="booking_completed", previous_status="executing", new_status="completed", safe_metadata={"slot_id": slot.slot_id}))
        return ToolResult(True, completed.action_reference, "completed", "Your meeting has been booked.", completed.result)


def _slot_to_dict(slot: AvailableSlot) -> dict[str, str]:
    return {"slot_id": slot.slot_id, "start_at": slot.start_at.isoformat(), "end_at": slot.end_at.isoformat(), "timezone": slot.timezone}


def _slot_from_dict(value: dict[str, str]) -> AvailableSlot:
    return AvailableSlot(value["slot_id"], start_at=__import__("datetime").datetime.fromisoformat(value["start_at"]), end_at=__import__("datetime").datetime.fromisoformat(value["end_at"]), timezone=value["timezone"])
