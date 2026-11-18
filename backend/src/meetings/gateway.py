from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .availability import MeetingScheduleConfig, generate_slots
from .models import AvailabilityRequest, AvailabilityResult, BookingRequest, BookingResult


class CalendarIntegrationNotConfigured(RuntimeError):
    pass


class CalendarGateway(Protocol):
    def get_availability(self, request: AvailabilityRequest) -> AvailabilityResult: ...
    def create_meeting(self, request: BookingRequest) -> BookingResult: ...


class MockCalendarGateway:
    def __init__(self, busy_intervals: list[tuple[datetime, datetime]] | None = None, fail_booking: bool = False, config: MeetingScheduleConfig | None = None) -> None:
        self.busy_intervals = busy_intervals or []
        self.fail_booking = fail_booking
        self.config = config or MeetingScheduleConfig.from_env()
        self.created: dict[str, BookingResult] = {}

    def get_availability(self, request: AvailabilityRequest) -> AvailabilityResult:
        slots = generate_slots(request.requested_date, self.busy_intervals, self.config)
        if request.daypart == "afternoon":
            slots = [slot for slot in slots if slot.start_at.hour >= 12]
        elif request.daypart == "morning":
            slots = [slot for slot in slots if slot.start_at.hour < 12]
        return AvailabilityResult(success=True, slots=slots)

    def create_meeting(self, request: BookingRequest) -> BookingResult:
        if request.action_reference in self.created:
            return self.created[request.action_reference]
        if self.fail_booking:
            return BookingResult(success=False, status="failed", error_code="mock_calendar_failure")
        result = BookingResult(
            success=True,
            status="booked",
            external_event_id=f"mock_event_{request.action_reference}",
            external_event_url=None,
        )
        self.created[request.action_reference] = result
        return result
