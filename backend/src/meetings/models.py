from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal


MeetingStatus = Literal["requested", "slot_offered", "awaiting_confirmation", "confirmed", "booked", "failed", "cancelled"]


@dataclass(frozen=True)
class AvailabilityRequest:
    conversation_id: str
    requested_date: date
    timezone: str = "Asia/Karachi"
    daypart: str | None = None


@dataclass(frozen=True)
class AvailableSlot:
    slot_id: str
    start_at: datetime
    end_at: datetime
    timezone: str


@dataclass(frozen=True)
class AvailabilityResult:
    success: bool
    slots: list[AvailableSlot] = field(default_factory=list)
    error_code: str | None = None


@dataclass(frozen=True)
class BookingRequest:
    action_reference: str
    conversation_id: str
    lead_id: str | None
    email: str
    full_name: str | None
    slot: AvailableSlot


@dataclass(frozen=True)
class BookingResult:
    success: bool
    status: str
    external_event_id: str | None = None
    external_event_url: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class SalesMeeting:
    meeting_reference: str
    action_id: str
    conversation_id: str
    timezone: str
    duration_minutes: int
    buffer_minutes: int
    id: str | None = None
    lead_id: str | None = None
    requested_date: date | None = None
    requested_daypart: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    calendar_provider: str | None = None
    external_event_id: str | None = None
    external_event_url: str | None = None
    status: MeetingStatus = "requested"
