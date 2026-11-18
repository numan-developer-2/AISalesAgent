from __future__ import annotations

from meetings.gateway import CalendarGateway, CalendarIntegrationNotConfigured

from .config import GoogleCalendarConfig
from .gateway import GoogleCalendarGateway


def create_calendar_gateway(config: GoogleCalendarConfig | None = None) -> CalendarGateway:
    resolved = config or GoogleCalendarConfig.from_env()
    if not resolved.enabled:
        raise CalendarIntegrationNotConfigured("Google Calendar is disabled")
    return GoogleCalendarGateway(resolved)
