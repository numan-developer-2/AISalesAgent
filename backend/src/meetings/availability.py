from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import AvailableSlot


@dataclass(frozen=True)
class MeetingScheduleConfig:
    timezone: str = "Asia/Karachi"
    workday_start: str = "10:00"
    workday_end: str = "18:00"
    duration_minutes: int = 30
    buffer_minutes: int = 15
    working_weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)

    @classmethod
    def from_env(cls) -> "MeetingScheduleConfig":
        return cls(
            timezone=os.getenv("GOOGLE_CALENDAR_TIMEZONE", "Asia/Karachi"),
            workday_start=os.getenv("SALES_WORKDAY_START", "10:00"),
            workday_end=os.getenv("SALES_WORKDAY_END", "18:00"),
            duration_minutes=int(os.getenv("MEETING_DURATION_MINUTES", "30")),
            buffer_minutes=int(os.getenv("MEETING_BUFFER_MINUTES", "15")),
        )


def generate_slots(day: date, busy_intervals: list[tuple[datetime, datetime]], config: MeetingScheduleConfig) -> list[AvailableSlot]:
    if day.weekday() not in config.working_weekdays:
        return []
    tz = ZoneInfo(config.timezone)
    start = datetime.combine(day, _parse_time(config.workday_start), tz)
    end = datetime.combine(day, _parse_time(config.workday_end), tz)
    duration = timedelta(minutes=config.duration_minutes)
    step = duration + timedelta(minutes=config.buffer_minutes)
    normalized_busy = _merge_intervals([(s.astimezone(tz), e.astimezone(tz)) for s, e in busy_intervals])
    slots: list[AvailableSlot] = []
    cursor = start
    index = 1
    while cursor + duration <= end:
        slot_end = cursor + duration
        blocked = any(cursor < busy_end + timedelta(minutes=config.buffer_minutes) and slot_end > busy_start - timedelta(minutes=config.buffer_minutes) for busy_start, busy_end in normalized_busy)
        if not blocked:
            slot_id = f"{day.isoformat()}-{index:02d}"
            slots.append(AvailableSlot(slot_id=slot_id, start_at=cursor, end_at=slot_end, timezone=config.timezone))
            index += 1
        cursor += step
    return slots


def _parse_time(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def _merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    ordered = sorted((s, e) for s, e in intervals if e > s)
    merged: list[tuple[datetime, datetime]] = []
    for start, end in ordered:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        elif end > merged[-1][1]:
            merged[-1] = (merged[-1][0], end)
    return merged
