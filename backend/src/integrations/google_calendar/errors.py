from __future__ import annotations


class CalendarIntegrationError(RuntimeError):
    safe_code = "calendar_integration_error"


class CalendarConfigurationError(CalendarIntegrationError):
    safe_code = "calendar_configuration_error"


class CalendarAuthenticationRequired(CalendarIntegrationError):
    safe_code = "calendar_authentication_required"


class CalendarPermissionDenied(CalendarIntegrationError):
    safe_code = "calendar_permission_denied"


class CalendarRateLimited(CalendarIntegrationError):
    safe_code = "calendar_rate_limited"


class CalendarTemporarilyUnavailable(CalendarIntegrationError):
    safe_code = "calendar_temporarily_unavailable"


class CalendarNotFound(CalendarIntegrationError):
    safe_code = "calendar_not_found"


class CalendarBookingFailed(CalendarIntegrationError):
    safe_code = "calendar_booking_failed"


class CalendarSlotUnavailable(CalendarIntegrationError):
    safe_code = "selected_slot_no_longer_available"
