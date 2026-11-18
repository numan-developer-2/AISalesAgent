from __future__ import annotations

import re


def page_quality(page: dict) -> tuple[int, list[str]]:
    warnings = []
    score = 100
    text = page.get("clean_text", "")
    if not page.get("title"):
        score -= 10
        warnings.append("missing_title")
    if len(text.split()) < 80 and page.get("page_type") not in {"contact", "legal"}:
        score -= 30
        warnings.append("low_clean_word_count")
    if not page.get("headings"):
        score -= 10
        warnings.append("missing_headings")
    if re.search(r"function\s*\(|var\s+|\.elementor-|wp-content/plugins", text):
        score -= 20
        warnings.append("possible_js_css_contamination")
    if not page.get("canonical_url"):
        score -= 5
        warnings.append("missing_canonical")
    if page.get("page_type") == "unknown":
        score -= 15
        warnings.append("unknown_classification")
    return max(0, min(100, score)), warnings


def build_review_queue(pages: list[dict], pricing: list[dict], errors: list[dict]) -> list[dict]:
    review = []
    pricing_sources = {price.get("source_url") for price in pricing}
    for page in pages:
        reasons = []
        if page.get("quality_score", 0) < 60:
            reasons.append("quality_score_below_60")
        if page.get("page_type") == "unknown":
            reasons.append("classification_confidence_low")
        if page.get("needs_review"):
            reasons.append("page_marked_needs_review")
        text = page.get("clean_text", "")
        if page.get("url") not in pricing_sources and re.search(r"\b(price|pricing|package|packages|plan|quote)\b", text, re.I):
            reasons.append("pricing_or_package_text_without_public_amount")
        if reasons:
            review.append({"type": "page", "url": page["url"], "reasons": reasons, "quality_score": page.get("quality_score")})
    for price in pricing:
        if price.get("needs_review"):
            review.append({"type": "pricing", "url": price["source_url"], "reasons": ["ambiguous_pricing_context"], "price_text_original": price.get("price_text_original", "")[:300]})
    for error in errors:
        review.append({"type": "error", "url": error.get("url"), "reasons": [error.get("error_type", "fetch_error")], "error_message": error.get("error_message", "")})
    return review


def validate_outputs(pages: list[dict], services: list[dict], faqs: list[dict], pricing: list[dict], chunks: list[dict], company_profile: dict) -> list[str]:
    warnings = []
    if not any(p["page_type"] == "homepage" for p in pages):
        warnings.append("homepage_not_scraped")
    if not company_profile.get("emails") and not company_profile.get("phone_numbers"):
        warnings.append("contact_details_not_found")
    if not services:
        warnings.append("no_services_found")
    if not faqs:
        warnings.append("no_faqs_found")
    if not pricing:
        warnings.append("no_public_pricing_found")
    if any(not c.get("url") or not c.get("content_hash") for c in chunks):
        warnings.append("rag_chunk_metadata_incomplete")
    return warnings
