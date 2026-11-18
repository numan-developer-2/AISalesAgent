from __future__ import annotations

from dataclasses import replace

from .models import LeadProfile, ScoreReason


SUPPORTED_SERVICE_TERMS = {
    "seo", "local seo", "google ads", "ppc", "web design", "website", "wordpress",
    "shopify", "digital marketing", "social media", "email marketing", "lead generation",
}


def classify_score(score: int) -> str:
    score = max(0, min(100, score))
    if score >= 70:
        return "Hot"
    if score >= 40:
        return "Warm"
    return "Cold"


class LeadScorer:
    def score(self, lead: LeadProfile, meaningful_messages: int = 0, buying_signal: str = "none") -> LeadProfile:
        reasons = [
            self._service_fit(lead),
            self._purchase_intent(lead, buying_signal),
            self._urgency(lead),
            self._budget_authority(lead),
            self._engagement(meaningful_messages, lead),
            self._contact_completeness(lead),
        ]
        total = max(0, min(100, sum(reason.score for reason in reasons)))
        return replace(lead, lead_score=total, lead_classification=classify_score(total), score_reasons=reasons)

    def _service_fit(self, lead: LeadProfile) -> ScoreReason:
        text = " ".join([*lead.required_services, lead.business_goal or "", lead.industry or ""]).lower()
        if any(term in text for term in SUPPORTED_SERVICE_TERMS):
            return ScoreReason("service_fit", 25, "Lead need maps to a supported service")
        if lead.business_goal:
            return ScoreReason("service_fit", 5, "Lead provided a vague business-growth need")
        return ScoreReason("service_fit", 0, "No supported service need identified")

    def _purchase_intent(self, lead: LeadProfile, buying_signal: str) -> ScoreReason:
        if lead.proposal_requested or lead.meeting_requested or lead.human_handover_requested:
            return ScoreReason("purchase_intent", 20, "Lead requested proposal, meeting, or human handover")
        if lead.budget_range or buying_signal in ("medium", "high"):
            return ScoreReason("purchase_intent", 12, "Lead showed pricing or buying interest")
        if lead.required_services or lead.business_goal:
            return ScoreReason("purchase_intent", 5, "Lead showed exploratory service interest")
        return ScoreReason("purchase_intent", 0, "No buying intent identified")

    def _urgency(self, lead: LeadProfile) -> ScoreReason:
        text = (lead.timeline or "").lower()
        if any(term in text for term in ("asap", "immediate", "within 30", "this month", "within a month")):
            return ScoreReason("urgency", 20, "Lead indicated immediate or within-30-days timeline")
        if any(term in text for term in ("1-3", "1 to 3", "three months", "quarter")):
            return ScoreReason("urgency", 12, "Lead indicated 1-3 month timeline")
        if any(term in text for term in ("later", "future", "exploring")):
            return ScoreReason("urgency", 5, "Lead indicated later or exploratory timing")
        return ScoreReason("urgency", 0, "No timeline evidence")

    def _budget_authority(self, lead: LeadProfile) -> ScoreReason:
        has_budget = bool(lead.budget_range)
        has_authority = bool(lead.authority_status and any(t in lead.authority_status.lower() for t in ("owner", "decision", "founder", "approve")))
        if has_budget and has_authority:
            return ScoreReason("budget_authority", 15, "Lead provided budget and decision authority")
        if has_budget or has_authority:
            return ScoreReason("budget_authority", 10, "Lead provided budget or authority signal")
        return ScoreReason("budget_authority", 0, "No budget or authority signal")

    def _engagement(self, meaningful_messages: int, lead: LeadProfile) -> ScoreReason:
        supplied = sum(bool(v) for v in [lead.business_goal, lead.industry, lead.timeline, lead.company_name])
        if meaningful_messages >= 3 and supplied >= 2:
            return ScoreReason("engagement", 10, "Multiple meaningful exchanges with discovery information")
        if meaningful_messages >= 2:
            return ScoreReason("engagement", 7, "Several meaningful interactions")
        if meaningful_messages >= 1:
            return ScoreReason("engagement", 4, "One substantive sales message")
        return ScoreReason("engagement", 0, "No meaningful engagement")

    def _contact_completeness(self, lead: LeadProfile) -> ScoreReason:
        score = 0
        score += 2 if lead.full_name else 0
        score += 3 if lead.email else 0
        score += 3 if lead.phone else 0
        score += 1 if lead.company_name else 0
        score += 1 if lead.website_url else 0
        return ScoreReason("contact_completeness", score, "Contact completeness calculated from validated fields")
