from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal


LeadClassification = Literal["Hot", "Warm", "Cold"]
ConsentStatus = Literal["not_requested", "granted", "declined"]


@dataclass(frozen=True)
class ScoreReason:
    component: str
    score: int
    reason: str


@dataclass(frozen=True)
class LeadUpdate:
    full_name: str | None = None
    company_name: str | None = None
    email: str | None = None
    phone: str | None = None
    website_url: str | None = None
    industry: str | None = None
    required_services: list[str] = field(default_factory=list)
    business_goal: str | None = None
    budget_range: str | None = None
    timeline: str | None = None
    authority_status: str | None = None


@dataclass(frozen=True)
class LeadProfile:
    lead_reference: str
    id: str | None = None
    full_name: str | None = None
    company_name: str | None = None
    email: str | None = None
    phone: str | None = None
    website_url: str | None = None
    industry: str | None = None
    required_services: list[str] = field(default_factory=list)
    business_goal: str | None = None
    budget_range: str | None = None
    timeline: str | None = None
    authority_status: str | None = None
    lead_score: int = 0
    lead_classification: LeadClassification = "Cold"
    score_reasons: list[ScoreReason] = field(default_factory=list)
    meeting_requested: bool = False
    proposal_requested: bool = False
    human_handover_requested: bool = False
    assigned_sales_rep: str | None = None
    crm_status: str = "New"
    source_page: str | None = None
    language: str | None = None
    consent_status: ConsentStatus = "not_requested"

    def __post_init__(self) -> None:
        if self.lead_score < 0 or self.lead_score > 100:
            raise ValueError("lead_score must be between 0 and 100")
        if self.lead_classification not in ("Hot", "Warm", "Cold"):
            raise ValueError("invalid lead_classification")
        if self.consent_status not in ("not_requested", "granted", "declined"):
            raise ValueError("invalid consent_status")

    def merge(self, update: LeadUpdate, explicit_corrections: bool = False) -> "LeadProfile":
        values: dict[str, Any] = {}
        for field_name in (
            "full_name",
            "company_name",
            "email",
            "phone",
            "website_url",
            "industry",
            "business_goal",
            "budget_range",
            "timeline",
            "authority_status",
        ):
            incoming = getattr(update, field_name)
            current = getattr(self, field_name)
            if incoming and (not current or explicit_corrections):
                values[field_name] = incoming
        if update.required_services:
            merged = list(dict.fromkeys([*self.required_services, *update.required_services]))
            values["required_services"] = merged
        return replace(self, **values)

    def to_record(self) -> dict[str, Any]:
        return {
            "lead_reference": self.lead_reference,
            "full_name": self.full_name,
            "company_name": self.company_name,
            "email": self.email,
            "phone": self.phone,
            "website_url": self.website_url,
            "industry": self.industry,
            "required_services": self.required_services,
            "business_goal": self.business_goal,
            "budget_range": self.budget_range,
            "timeline": self.timeline,
            "authority_status": self.authority_status,
            "lead_score": self.lead_score,
            "lead_classification": self.lead_classification,
            "score_reasons": [reason.__dict__ for reason in self.score_reasons],
            "meeting_requested": self.meeting_requested,
            "proposal_requested": self.proposal_requested,
            "human_handover_requested": self.human_handover_requested,
            "assigned_sales_rep": self.assigned_sales_rep,
            "crm_status": self.crm_status,
            "source_page": self.source_page,
            "language": self.language,
            "consent_status": self.consent_status,
        }
