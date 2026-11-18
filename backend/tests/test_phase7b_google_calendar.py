from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest


BACKEND_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(BACKEND_SRC))

from integrations.google_calendar.auth import load_authorized_credentials
from integrations.google_calendar.config import GoogleCalendarConfig
from integrations.google_calendar.errors import CalendarAuthenticationRequired, CalendarConfigurationError
from integrations.google_calendar.factory import create_calendar_gateway
from integrations.google_calendar.gateway import GoogleCalendarGateway, SAFE_EVENT_SUMMARY
from leads.models import LeadProfile
from meetings.gateway import CalendarIntegrationNotConfigured
from meetings.models import AvailabilityRequest, AvailableSlot, BookingRequest
from meetings.service import MeetingBookingService
from tools.repository import InMemoryActionAuditRepository, InMemoryActionRepository


class FakeExecute:
    def __init__(self, response):
        self.response = response

    def execute(self):
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeFreebusy:
    def __init__(self, service):
        self.service = service

    def query(self, body):
        self.service.freebusy_body = body
        return FakeExecute(self.service.freebusy_response)


class FakeEvents:
    def __init__(self, service):
        self.service = service

    def insert(self, calendarId, body, sendUpdates=None):
        self.service.insert_calls += 1
        self.service.insert_calendar_id = calendarId
        self.service.insert_body = body
        return FakeExecute(self.service.insert_response)


class FakeGoogleService:
    def __init__(self, calendar_id="calendar@example.com", busy=None, insert_response=None):
        self.calendar_id = calendar_id
        self.freebusy_response = {"calendars": {calendar_id: {"busy": busy or []}}}
        self.insert_response = insert_response or {"id": "event_1", "htmlLink": "https://calendar.test/event_1"}
        self.insert_calls = 0
        self.freebusy_body = None
        self.insert_body = None
        self.insert_calendar_id = None

    def freebusy(self):
        return FakeFreebusy(self)

    def events(self):
        return FakeEvents(self)


def config(enabled=True, calendar_id="calendar@example.com") -> GoogleCalendarConfig:
    return GoogleCalendarConfig(enabled=enabled, calendar_id=calendar_id, timezone="Asia/Karachi")


def test_disabled_gateway_fails_closed() -> None:
    with pytest.raises(CalendarIntegrationNotConfigured):
        create_calendar_gateway(config(enabled=False))


def test_enabled_gateway_requires_calendar_id() -> None:
    with pytest.raises(CalendarConfigurationError):
        GoogleCalendarGateway(config(enabled=True, calendar_id=""), service=FakeGoogleService())


def test_missing_token_raises_authentication_required(tmp_path) -> None:
    with pytest.raises(CalendarAuthenticationRequired):
        load_authorized_credentials(tmp_path / "missing_token.json")


def test_freebusy_uses_configured_calendar_id_timezone_and_normalizes_busy() -> None:
    tz = ZoneInfo("Asia/Karachi")
    busy = [{"start": datetime(2026, 8, 21, 10, 0, tzinfo=tz).isoformat(), "end": datetime(2026, 8, 21, 10, 30, tzinfo=tz).isoformat()}]
    fake = FakeGoogleService(busy=busy)
    gateway = GoogleCalendarGateway(config(), service=fake)
    intervals = gateway.get_busy_intervals(datetime(2026, 8, 21, 0, 0, tzinfo=tz), datetime(2026, 8, 21, 23, 59, tzinfo=tz), "Asia/Karachi")
    assert fake.freebusy_body["items"] == [{"id": "calendar@example.com"}]
    assert fake.freebusy_body["timeZone"] == "Asia/Karachi"
    assert intervals[0][0].tzinfo is not None


def test_availability_reuses_local_slot_engine() -> None:
    fake = FakeGoogleService()
    gateway = GoogleCalendarGateway(config(), service=fake)
    result = gateway.get_availability(AvailabilityRequest("conv", date(2026, 8, 21), "Asia/Karachi"))
    assert result.success
    assert result.slots


def test_event_fields_are_safe_and_attendee_is_validated() -> None:
    fake = FakeGoogleService()
    gateway = GoogleCalendarGateway(config(), service=fake)
    tz = ZoneInfo("Asia/Karachi")
    slot = AvailableSlot("slot-1", datetime(2026, 8, 21, 11, 0, tzinfo=tz), datetime(2026, 8, 21, 11, 30, tzinfo=tz), "Asia/Karachi")
    result = gateway.create_meeting(BookingRequest("act", "conv", "lead", "qa@example.com", "QA Visitor", slot))
    assert result.success
    assert fake.insert_calendar_id == "calendar@example.com"
    assert fake.insert_body["summary"].startswith(SAFE_EVENT_SUMMARY)
    assert fake.insert_body["attendees"] == [{"email": "qa@example.com"}]
    assert "RAG" not in fake.insert_body["description"]


def test_busy_after_offer_prevents_insert() -> None:
    tz = ZoneInfo("Asia/Karachi")
    busy = [{"start": datetime(2026, 8, 21, 11, 0, tzinfo=tz).isoformat(), "end": datetime(2026, 8, 21, 11, 30, tzinfo=tz).isoformat()}]
    fake = FakeGoogleService(busy=busy)
    gateway = GoogleCalendarGateway(config(), service=fake)
    slot = AvailableSlot("slot-1", datetime(2026, 8, 21, 11, 0, tzinfo=tz), datetime(2026, 8, 21, 11, 30, tzinfo=tz), "Asia/Karachi")
    result = gateway.create_meeting(BookingRequest("act", "conv", "lead", "qa@example.com", None, slot))
    assert result.success is False
    assert result.error_code == "selected_slot_no_longer_available"
    assert fake.insert_calls == 0


def test_booking_persists_event_id_and_duplicate_does_not_insert_again() -> None:
    fake = FakeGoogleService()
    gateway = GoogleCalendarGateway(config(), service=fake)
    actions = InMemoryActionRepository()
    service = MeetingBookingService(actions, InMemoryActionAuditRepository(), gateway)
    tz = ZoneInfo("Asia/Karachi")
    slot = AvailableSlot("slot-1", datetime(2026, 8, 21, 11, 0, tzinfo=tz), datetime(2026, 8, 21, 11, 30, tzinfo=tz), "Asia/Karachi")
    lead = LeadProfile(id="lead", lead_reference="lead", email="qa@example.com")
    offer = service.offer_booking_slot("conv", lead, slot, [slot])
    booked = service.confirm_and_book(offer.action_reference, "Yes, book it", "slot-1", lead)
    duplicate = service.confirm_and_book(offer.action_reference, "Yes, book it", "slot-1", lead)
    assert booked.data["external_event_id"] == "event_1"
    assert duplicate.data["external_event_id"] == "event_1"
    assert fake.insert_calls == 1


def test_invalid_email_does_not_call_insert() -> None:
    fake = FakeGoogleService()
    gateway = GoogleCalendarGateway(config(), service=fake)
    tz = ZoneInfo("Asia/Karachi")
    slot = AvailableSlot("slot-1", datetime(2026, 8, 21, 11, 0, tzinfo=tz), datetime(2026, 8, 21, 11, 30, tzinfo=tz), "Asia/Karachi")
    result = gateway.create_meeting(BookingRequest("act", "conv", "lead", "not-email", None, slot))
    assert result.success is False
    assert fake.insert_calls == 0
