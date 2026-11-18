from __future__ import annotations

import re

from src.utils.hashing import sha256_text, stable_id


def estimate_tokens(text: str) -> int:
    return max(1, len(re.findall(r"\S+", text)) * 4 // 3)


def chunk_page(page: dict, scraped_at: str, target_tokens: int = 700, overlap_tokens: int = 100) -> list[dict]:
    text = page.get("clean_text", "")
    sections = _semantic_sections(text)
    chunks = []
    for heading, section_text in sections:
        words = section_text.split()
        if not words:
            continue
        max_words = max(180, target_tokens * 3 // 4)
        overlap_words = overlap_tokens * 3 // 4
        start = 0
        while start < len(words):
            part_words = words[start:start + max_words]
            part = " ".join(part_words).strip()
            if len(part) > 80:
                content_type = _content_type(page.get("page_type", ""), heading, part)
                chunks.append({
                    "chunk_id": stable_id("chunk", f"{page['id']}|{heading}|{start}|{sha256_text(part)}"),
                    "document_id": page["id"],
                    "url": page["url"],
                    "page_title": page["title"],
                    "page_type": page["page_type"],
                    "service": page.get("service_name", ""),
                    "category": page.get("service_category", ""),
                    "heading": heading,
                    "content_type": content_type,
                    "text": part,
                    "token_estimate": estimate_tokens(part),
                    "source_priority": page["source_priority"],
                    "scraped_at": scraped_at,
                    "content_hash": sha256_text(part),
                })
            if start + max_words >= len(words):
                break
            start += max_words - overlap_words
    return chunks


def _semantic_sections(text: str) -> list[tuple[str, str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    sections = []
    current_heading = "Overview"
    current = []
    for line in lines:
        if len(line) < 90 and not line.endswith(".") and len(line.split()) <= 10:
            if current:
                sections.append((current_heading, "\n".join(current)))
                current = []
            current_heading = line
        else:
            current.append(line)
    if current:
        sections.append((current_heading, "\n".join(current)))
    return sections or [("Overview", text)]


def _content_type(page_type: str, heading: str, text: str) -> str:
    haystack = f"{heading} {text}".lower()
    if "faq" in haystack or "?" in heading:
        return "faq"
    if re.search(r"price|pricing|package|plan|\$|usd|pkr", haystack):
        return "pricing"
    if re.search(r"process|how it works|step", haystack):
        return "process"
    if re.search(r"timeline|weeks|months|days", haystack):
        return "timeline"
    if re.search(r"testimonial|review", haystack):
        return "testimonial"
    if page_type in {"portfolio", "case_study"}:
        return "case_study"
    if page_type == "blog":
        return "blog"
    if page_type in {"about", "homepage", "contact"}:
        return "company_information"
    return "service_overview" if page_type in {"service", "service_subpage"} else page_type or "company_information"
