from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ProposalGatewayResult:
    success: bool
    status: str = "pending_delivery"
    proposal_request_reference: str | None = None
    error_code: str | None = None
    safe_metadata: dict[str, str] = field(default_factory=dict)


class ProposalGateway(Protocol):
    def request_proposal(self, action_reference: str, lead_reference: str, services: list[str], contact_method: str) -> ProposalGatewayResult: ...


class MockProposalGateway:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.created: dict[str, ProposalGatewayResult] = {}

    def request_proposal(self, action_reference: str, lead_reference: str, services: list[str], contact_method: str) -> ProposalGatewayResult:
        if action_reference in self.created:
            return self.created[action_reference]
        if self.fail:
            return ProposalGatewayResult(False, status="failed", error_code="mock_proposal_failure")
        result = ProposalGatewayResult(True, proposal_request_reference=f"proposal_{action_reference}", safe_metadata={"service_count": str(len(services)), "contact_method": contact_method})
        self.created[action_reference] = result
        return result
