from __future__ import annotations

from datetime import datetime
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from leads.extraction import normalize_email
from meetings.availability import MeetingScheduleConfig, generate_slots
from meetings.gateway import CalendarGateway
from meetings.models import AvailabilityRequest, AvailabilityResult, BookingRequest, BookingResult

from .auth import load_authorized_credentials
from .config import GoogleCalendarConfig
from .errors import (
    CalendarAuthenticationRequired,
    CalendarBookingFailed,
    CalendarConfigurationError,
    CalendarIntegrationError,
    CalendarNotFound,
    CalendarPermissionDenied,
    CalendarRateLimited,
    CalendarSlotUnavailable,
    CalendarTemporarilyUnavailable,
)


SAFE_EVENT_SUMMARY = "Systematic Demo Studio — Sales Consultation"
QA_EVENT_SUMMARY = "QA — Systematic AI Sales Agent Test Meeting"


class GoogleCalendarGateway(CalendarGateway):
    def __init__(self, config: GoogleCalendarConfig | None = None, service: Any | None = None, schedule: MeetingScheduleConfig | None = None) -> None:
        self.config = config or GoogleCalendarConfig.from_env()
        self.schedule = schedule or MeetingScheduleConfig.from_env()
        if not self.config.enabled:
            raise CalendarConfigurationError("Google Calendar is disabled")
        if not self.config.calendar_id:
            raise CalendarConfigurationError("GOOGLE_CALENDAR_ID is required")
        self.service = service or build("calendar", "v3", credentials=load_authorized_credentials(self.config.token_file, self.config.scopes), cache_discovery=False)

    def get_availability(self, request: AvailabilityRequest) -> AvailabilityResult:
        time_min, time_max = _day_bounds(request)
        busy = self.get_busy_intervals(time_min, time_max, request.timezone)
        config = MeetingScheduleConfig(
            timezone=request.timezone,
            workday_start=self.schedule.workday_start,
            workday_end=self.schedule.workday_end,
            duration_minutes=self.schedule.duration_minutes,
            buffer_minutes=self.schedule.buffer_minutes,
        )
        slots = generate_slots(request.requested_date, busy, config)
        if request.daypart == "morning":
            slots = [slot for slot in slots if slot.start_at.hour < 12]
        elif request.daypart == "afternoon":
            slots = [slot for slot in slots if slot.start_at.hour >= 12]
        return AvailabilityResult(True, slots)

    def get_busy_intervals(self, time_min: datetime, time_max: datetime, timezone: str) -> list[tuple[datetime, datetime]]:
        body = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "timeZone": timezone,
            "items": [{"id": self.config.calendar_id}],
        }
        try:
            response = self.service.freebusy().query(body=body).execute()
        except HttpError as exc:
            raise _map_google_error(exc) from exc
        calendars = response.get("calendars", {})
        calendar = calendars.get(self.config.calendar_id)
        if calendar is None:
            raise CalendarNotFound("Configured calendar was not returned by FreeBusy")
        if calendar.get("errors"):
            raise CalendarTemporarilyUnavailable("Calendar availability could not be verified")
        return [(datetime.fromisoformat(item["start"]), datetime.fromisoformat(item["end"])) for item in calendar.get("busy", [])]

    def create_meeting(self, request: BookingRequest) -> BookingResult:
        if not normalize_email(request.email):
            return BookingResult(False, "failed", error_code="valid_attendee_email_required")
        if not self._slot_is_free(request.slot.start_at, request.slot.end_at, request.slot.timezone):
            return BookingResult(False, "failed", error_code=CalendarSlotUnavailable.safe_code)
        event = {
            "summary": _safe_summary(request.full_name, request.conversation_id),
            "description": _safe_description(request),
            "start": {"dateTime": request.slot.start_at.isoformat(), "timeZone": request.slot.timezone},
            "end": {"dateTime": request.slot.end_at.isoformat(), "timeZone": request.slot.timezone},
            "attendees": [{"email": request.email}],
        }
        try:
            created = self.service.events().insert(calendarId=self.config.calendar_id, body=event, sendUpdates="all").execute()
        except HttpError as exc:
            error = _map_google_error(exc)
            return BookingResult(False, "failed", error_code=getattr(error, "safe_code", CalendarBookingFailed.safe_code))
        return BookingResult(True, "booked", external_event_id=created.get("id"), external_event_url=created.get("htmlLink"))

    def delete_qa_event(self, event_id: str, summary: str = QA_EVENT_SUMMARY) -> bool:
        if not event_id:
            raise CalendarBookingFailed("Refusing to delete event without event ID")
        event = self.service.events().get(calendarId=self.config.calendar_id, eventId=event_id).execute()
        if event.get("summary") != summary:
            raise CalendarBookingFailed("Refusing to delete event without QA summary")
        self.service.events().delete(calendarId=self.config.calendar_id, eventId=event_id).execute()
        return True

    def slot_is_free(self, start: datetime, end: datetime, timezone: str) -> bool:
        """Public availability contract; the caller supplies the business timezone."""
        return self._slot_is_free(start, end, timezone)

    def _slot_is_free(self, start: datetime, end: datetime, timezone: str) -> bool:
        return not self.get_busy_intervals(start, end, timezone)


def _day_bounds(request: AvailabilityRequest) -> tuple[datetime, datetime]:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(request.timezone)
    start = datetime.combine(request.requested_date, datetime.min.time(), tz)
    end = datetime.combine(request.requested_date, datetime.max.time(), tz)
    return start, end


def _safe_summary(name: str | None, conversation_id: str = "") -> str:
    if conversation_id.startswith("qa-"):
        return QA_EVENT_SUMMARY
    if name and len(name) <= 80:
        return f"{SAFE_EVENT_SUMMARY} — {name}"
    return SAFE_EVENT_SUMMARY


def _safe_description(request: BookingRequest) -> str:
    lines = [
        "Systematic AI Sales Agent booking.",
        f"Conversation reference: {request.conversation_id}",
    ]
    if request.lead_id:
        lines.append(f"Lead reference: {request.lead_id}")
    return "\n".join(lines)


def _map_google_error(exc: HttpError) -> CalendarIntegrationError:
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status in (401,):
        return CalendarAuthenticationRequired("Google Calendar authorization required")
    if status in (403,):
        return CalendarPermissionDenied("Google Calendar permission denied")
    if status in (404,):
        return CalendarNotFound("Configured Google Calendar not found")
    if status in (429,):
        return CalendarRateLimited("Google Calendar rate limited")
    if status in (500, 502, 503, 504):
        return CalendarTemporarilyUnavailable("Google Calendar temporarily unavailable")
    return CalendarBookingFailed("Google Calendar request failed")
