from __future__ import annotations

import re

from src.utils.hashing import stable_id


SECTION_PATTERNS = {
    "benefits": r"\b(benefit|why choose|advantages?)\b",
    "features": r"\b(feature|included|includes)\b",
    "deliverables": r"\b(deliverable|what you get|included)\b",
    "process": r"\b(process|how it works|steps|workflow|approach)\b",
    "timeline": r"\b(timeline|how long|weeks?|months?|days?)\b",
    "client_requirements": r"\b(requirements?|what we need|from client)\b",
}


def extract_service_record(page: dict, faqs: list[dict], pricing: list[dict], testimonials: list[dict]) -> dict | None:
    if page["page_type"] not in {"service", "service_subpage", "pricing"}:
        return None
    service_name = page.get("service_name") or page.get("title") or ""
    if not service_name:
        return None
    if service_name.strip().lower() in {"services", "portfolio"}:
        return None
    text = page.get("clean_text", "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    buckets = {key: [] for key in SECTION_PATTERNS}
    for i, line in enumerate(lines):
        lower = line.lower()
        for bucket, pattern in SECTION_PATTERNS.items():
            if re.search(pattern, lower):
                buckets[bucket].extend(lines[i + 1:i + 6])
    suitable_for = []
    if re.search(r"local business|near me|google business|gmb", text, re.I):
        suitable_for.append({"value": "local businesses", "derived_from_source": True})
    if re.search(r"e-?commerce|shopify|online store", text, re.I):
        suitable_for.append({"value": "e-commerce businesses", "derived_from_source": True})
    if re.search(r"startup|small business", text, re.I):
        suitable_for.append({"value": "startups or small businesses", "derived_from_source": True})
    title = page.get("title", "")
    aliases = []
    if title and title.lower() != service_name.lower():
        aliases.append(title)
    related = [cta["text"] for cta in page.get("cta", []) if re.search(r"learn more|service", cta.get("text", ""), re.I)]
    return {
        "service_id": stable_id("service", page["canonical_url"] or page["url"]),
        "service_name": service_name,
        "aliases": aliases,
        "category": page.get("service_category", ""),
        "parent_service": parent_service(service_name, page.get("service_category", "")),
        "description": page.get("summary", ""),
        "ideal_customers": suitable_for,
        "problems_solved": [],
        "benefits": _clean_bucket(buckets["benefits"]),
        "features": _clean_bucket(buckets["features"]),
        "deliverables": _clean_bucket(buckets["deliverables"]),
        "process": _clean_bucket(buckets["process"]),
        "client_requirements": _clean_bucket(buckets["client_requirements"]),
        "timeline": _clean_bucket(buckets["timeline"]),
        "pricing": pricing,
        "faqs": faqs,
        "related_services": [],
        "upsell_services": [],
        "cross_sell_services": [],
        "inferred_related_services": related,
        "case_studies": [],
        "testimonials": testimonials,
        "primary_url": page["url"],
        "supporting_urls": [],
        "source_confidence": "high" if len(text.split()) >= 80 else "medium",
        "suitable_for": suitable_for,
        "business_types": suitable_for,
        "goals_supported": [],
    }


def parent_service(service_name: str, category: str) -> str:
    lowered = service_name.lower()
    if any(term in lowered for term in ["local seo", "technical seo", "website seo", "seo audit", "link building", "pr outreach", "shopify seo"]):
        return "Search Engine Optimization"
    if any(term in lowered for term in ["google ads", "meta ads", "social media ads"]):
        return "Paid Advertising"
    if category in {"Development", "Digital Marketing", "Design / Branding", "SEO"}:
        return category
    return ""


def _clean_bucket(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        if 8 <= len(item) <= 300 and item.lower() not in seen:
            seen.add(item.lower())
            out.append(item)
    return out[:12]
