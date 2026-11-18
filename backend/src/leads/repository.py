from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv
from supabase import create_client

from .models import LeadProfile, ScoreReason


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class LeadRepository(Protocol):
    def get_by_id(self, lead_id: str) -> LeadProfile | None: ...
    def upsert(self, lead: LeadProfile) -> LeadProfile: ...


class InMemoryLeadRepository:
    def __init__(self) -> None:
        self.records: dict[str, LeadProfile] = {}

    def get_by_id(self, lead_id: str) -> LeadProfile | None:
        return self.records.get(lead_id)

    def upsert(self, lead: LeadProfile) -> LeadProfile:
        key = lead.id or lead.lead_reference
        stored = lead if lead.id else LeadProfile(**{**lead.__dict__, "id": key})
        self.records[key] = stored
        return stored


class SupabaseLeadRepository:
    def __init__(self) -> None:
        load_dotenv(PROJECT_ROOT / ".env")
        self.client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SECRET_KEY"))

    def get_by_id(self, lead_id: str) -> LeadProfile | None:
        res = self.client.table("sales_leads").select("*").eq("id", lead_id).limit(1).execute()
        return _from_record(res.data[0]) if res.data else None

    def upsert(self, lead: LeadProfile) -> LeadProfile:
        res = self.client.table("sales_leads").upsert(lead.to_record(), on_conflict="lead_reference").execute()
        return _from_record(res.data[0]) if res.data else lead


def _from_record(row: dict) -> LeadProfile:
    reasons = [ScoreReason(**item) for item in row.get("score_reasons", [])]
    return LeadProfile(
        id=row.get("id"),
        lead_reference=row["lead_reference"],
        full_name=row.get("full_name"),
        company_name=row.get("company_name"),
        email=row.get("email"),
        phone=row.get("phone"),
        website_url=row.get("website_url"),
        industry=row.get("industry"),
        required_services=row.get("required_services", []),
        business_goal=row.get("business_goal"),
        budget_range=row.get("budget_range"),
        timeline=row.get("timeline"),
        authority_status=row.get("authority_status"),
        lead_score=row.get("lead_score", 0),
        lead_classification=row.get("lead_classification", "Cold"),
        score_reasons=reasons,
        meeting_requested=row.get("meeting_requested", False),
        proposal_requested=row.get("proposal_requested", False),
        human_handover_requested=row.get("human_handover_requested", False),
        source_page=row.get("source_page"),
        language=row.get("language"),
        consent_status=row.get("consent_status", "not_requested"),
    )
