from __future__ import annotations

from difflib import SequenceMatcher


def dedupe_pages(pages: list[dict]) -> tuple[list[dict], list[dict]]:
    kept: list[dict] = []
    duplicates: list[dict] = []
    seen_hashes: dict[str, str] = {}
    for page in pages:
        digest = page.get("content_hash", "")
        if digest in seen_hashes:
            page["page_type"] = "duplicate"
            duplicates.append({"url": page["url"], "duplicate_of": seen_hashes[digest], "reason": "exact_content_hash"})
            continue
        near = _near_duplicate(page, kept)
        if near:
            page["page_type"] = "duplicate"
            duplicates.append({"url": page["url"], "duplicate_of": near, "reason": "near_duplicate"})
            continue
        seen_hashes[digest] = page["url"]
        kept.append(page)
    return kept, duplicates


def _near_duplicate(page: dict, kept: list[dict]) -> str:
    text = page.get("clean_text", "")[:5000]
    if len(text) < 500:
        return ""
    for other in kept:
        other_text = other.get("clean_text", "")[:5000]
        if abs(len(text) - len(other_text)) > max(1000, len(text) * 0.35):
            continue
        if SequenceMatcher(None, text, other_text).ratio() > 0.94:
            return other["url"]
    return ""
