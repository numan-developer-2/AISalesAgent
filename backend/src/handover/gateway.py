from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class HandoverGatewayResult:
    success: bool
    status: str = "queued"
    handover_reference: str | None = None
    error_code: str | None = None


class HandoverGateway(Protocol):
    def request_handover(self, action_reference: str, conversation_id: str, reason: str, priority: str) -> HandoverGatewayResult: ...


class MockHandoverGateway:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.created: dict[str, HandoverGatewayResult] = {}

    def request_handover(self, action_reference: str, conversation_id: str, reason: str, priority: str) -> HandoverGatewayResult:
        if action_reference in self.created:
            return self.created[action_reference]
        if self.fail:
            return HandoverGatewayResult(False, status="failed", error_code="mock_handover_failure")
        result = HandoverGatewayResult(True, handover_reference=f"handover_{action_reference}")
        self.created[action_reference] = result
        return result
