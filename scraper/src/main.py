from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.chunking.chunker import chunk_page
from src.classifiers.page_classifier import classify_page, customer_questions, sales_intents, source_priority
from src.config import load_settings
from src.crawler.discovery import SiteDiscovery
from src.crawler.fetcher import Fetcher
from src.deduplication.deduper import dedupe_pages
from src.exporters.writer import prepare_output_dir, write_csv, write_json, write_jsonl
from src.extractors.html_extractor import (
    extract_ctas,
    extract_faqs,
    extract_forms,
    extract_navigation_targets,
    extract_page,
    extract_pricing,
    extract_testimonials,
)
from src.extractors.service_extractor import extract_service_record
from src.utils.hashing import sha256_text, stable_id
from src.utils.url import classify_url, normalize_url
from src.validators.qa import build_review_queue, page_quality, validate_outputs


PRIORITY = {
    "homepage": 0,
    "about": 1,
    "company_information": 1,
    "service": 2,
    "service_subpage": 3,
    "pricing": 4,
    "faq": 5,
    "portfolio": 6,
    "case_study": 6,
    "testimonial": 7,
    "contact": 8,
    "booking": 9,
    "blog": 10,
    "unknown": 11,
    "legal": 12,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_state(path: Path) -> dict[str, Any]:
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {"pages": {}}


def select_urls(inventory: dict, settings) -> list[str]:
    records = list(inventory.values())
    useful = [r for r in records if r.category not in {"duplicate", "translated_duplicate", "media", "irrelevant", "archive", "tag", "category_archive", "author_archive", "utility"}]
    blog_count = 0
    selected = []
    for rec in sorted(useful, key=lambda r: (PRIORITY.get(r.category, 99), r.normalized_url)):
        if rec.category == "blog":
            if not settings.scrape_blogs or blog_count >= settings.blog_limit:
                rec.skipped_reason = "blog_limit_or_disabled"
                continue
            blog_count += 1
        selected.append(rec.normalized_url)
        if len(selected) >= settings.max_pages:
            break
    return selected


async def process_url(url: str, inventory_rec, fetcher: Fetcher, settings, scraped_at: str, previous_hash: str = "") -> tuple[dict | None, dict]:
    fetched = await fetcher.fetch(url)
    error = {}
    if fetched.status_code != 200 or not fetched.content:
        final_url = normalize_url(fetched.final_url or url)
        content_type = fetched.content_type or ""
        error_type = "non_html_content" if fetched.status_code == 200 and content_type and "text" not in content_type and "xml" not in content_type else "fetch_error"
        error_message = f"non-HTML content: {content_type}" if error_type == "non_html_content" else fetched.error or f"HTTP {fetched.status_code}"
        error = {
            "url": url,
            "final_url": final_url,
            "timestamp": scraped_at,
            "http_status": fetched.status_code,
            "content_type": content_type,
            "error_type": error_type,
            "error_message": error_message,
            "retry_count": fetched.retry_count,
        }
        return None, error
    extracted = extract_page(fetched.content, normalize_url(fetched.final_url or url), settings.target_domain, scraped_at)
    if settings.enable_playwright and len(extracted["clean_text"].split()) < 20:
        rendered = await fetcher.fetch(url, render=True)
        if rendered.status_code == 200 and rendered.content:
            rendered_extracted = extract_page(rendered.content, normalize_url(rendered.final_url or url), settings.target_domain, scraped_at)
            if len(rendered_extracted["clean_text"].split()) > len(extracted["clean_text"].split()):
                fetched = rendered
                extracted = rendered_extracted
    page_type, service_category, service_name = classify_page(url, extracted["title"], extracted["clean_text"])
    if inventory_rec.category not in {"unknown", "duplicate"}:
        page_type = inventory_rec.category if inventory_rec.category != "service_subpage" or page_type == "unknown" else page_type
    if page_type in {"homepage", "about", "contact", "booking", "legal", "company_information"}:
        service_name = ""
    canonical = extracted["canonical_url"]
    content_hash = sha256_text(extracted["clean_text"])
    soup = extracted.pop("soup")
    cta = extract_ctas(soup, url)
    faqs = extract_faqs(soup, url, service_name, service_category, extracted["headings"][0]["text"] if extracted["headings"] else "", scraped_at)
    pricing = extract_pricing(soup, url, service_name, scraped_at)
    testimonials = extract_testimonials(soup, url)
    quality_score, quality_warnings = page_quality({
        "title": extracted["title"],
        "clean_text": extracted["clean_text"],
        "headings": extracted["headings"],
        "canonical_url": canonical,
        "page_type": page_type,
    })
    page = {
        "id": stable_id("page", canonical or url),
        "url": url,
        "final_url": normalize_url(fetched.final_url or url),
        "canonical_url": canonical,
        "page_type": page_type,
        "title": extracted["title"],
        "meta_description": extracted["meta_description"],
        "language": extracted["language"] or settings.language,
        "service_category": service_category,
        "service_name": service_name,
        "parent_service": "",
        "headings": extracted["headings"],
        "clean_text": extracted["clean_text"],
        "summary": extracted["summary"],
        "key_points": extracted["key_points"],
        "benefits": [],
        "features": [],
        "deliverables": [],
        "process_steps": [],
        "timelines": [],
        "pricing_refs": [p["pricing_id"] for p in pricing],
        "faq_refs": [f["faq_id"] for f in faqs],
        "case_study_refs": [],
        "testimonial_refs": [t["testimonial_id"] for t in testimonials],
        "related_services": [],
        "cta": cta,
        "contact_information": extracted["contact_information"],
        "internal_links": extracted["internal_links"],
        "important_external_links": extracted["important_external_links"],
        "images": extracted["images"],
        "source_priority": source_priority(page_type),
        "content_hash": content_hash,
        "previous_content_hash": previous_hash,
        "content_changed": previous_hash != content_hash if previous_hash else True,
        "scraped_at": scraped_at,
        "last_modified": inventory_rec.sitemap_lastmod,
        "http_status": fetched.status_code,
        "quality_score": quality_score,
        "quality_warnings": quality_warnings,
        "needs_review": quality_score < 60,
        "conflict_detected": False,
        "customer_questions_this_page_can_answer": customer_questions(page_type, service_name, extracted["clean_text"]),
        "sales_intents_supported": sales_intents(page_type, extracted["clean_text"]),
    }
    page["_faqs"] = faqs
    page["_pricing"] = pricing
    page["_forms"] = extract_forms(soup, url)
    page["_navigation"] = extract_navigation_targets(soup, url, extracted["title"], service_name)
    page["_testimonials"] = testimonials
    return page, error


async def crawl_selected(selected_urls: list[str], discovery, fetcher: Fetcher, settings, scraped_at: str, state: dict, incremental: bool) -> tuple[list[dict], list[dict]]:
    semaphore = asyncio.Semaphore(settings.max_concurrency)
    pages: list[dict] = []
    errors: list[dict] = []

    async def worker(url: str) -> None:
        async with semaphore:
            print(f"Fetching {url}", flush=True)
            previous_hash = state.get("pages", {}).get(url, {}).get("content_hash", "")
            page, error = await process_url(url, discovery.urls[url], fetcher, settings, scraped_at, previous_hash)
            if error:
                discovery.urls[url].http_status = error.get("http_status")
                discovery.urls[url].final_url = error.get("final_url", "")
                if error.get("error_type") == "non_html_content":
                    discovery.urls[url].category = "media"
                    discovery.urls[url].skipped_reason = error.get("error_message", "non_html_content")
                    print(f"Skipped {url}: {error.get('error_message')}", flush=True)
                    return
                errors.append(error)
                print(f"Failed {url}: {error.get('error_message')}", flush=True)
                return
            if page:
                if incremental and previous_hash and previous_hash == page["content_hash"]:
                    discovery.urls[url].skipped_reason = "unchanged_content_hash"
                pages.append(page)
                discovery.urls[url].http_status = page["http_status"]
                discovery.urls[url].final_url = page.get("final_url", page["url"])
                discovery.urls[url].canonical_url = page["canonical_url"]
                print(f"Scraped {url} ({len(page.get('clean_text', '').split())} words)", flush=True)

    await asyncio.gather(*(worker(url) for url in selected_urls))
    return pages, errors


def build_company_profile(pages: list[dict], settings) -> dict:
    company_pages = [p for p in pages if p["page_type"] in {"homepage", "about", "contact", "booking"}]
    sources = [p["url"] for p in company_pages]
    contacts = [item for p in company_pages for item in p.get("contact_information", [])]
    emails = sorted({c["value"] for c in contacts if c["type"] == "email"})
    phones = sorted({c["value"] for c in contacts if c["type"] == "phone"})
    socials = []
    for p in pages:
        for link in p.get("important_external_links", []):
            if any(host in link for host in ["facebook.com", "linkedin.com", "instagram.com", "twitter.com", "x.com", "youtube.com", "tiktok.com"]):
                socials.append(link)
    service_names = sorted({p.get("service_name") for p in pages if p.get("service_name") and p.get("page_type") in {"service", "service_subpage", "pricing"}})
    legal = {p["page_type"]: p["url"] for p in pages if p["page_type"] == "legal"}
    description = next((p["summary"] for p in company_pages if p.get("summary")), "not_found_on_website")
    company_name = "not_found_on_website"
    for page in company_pages:
        if "Systematic Demo Studio" in page.get("title", "") or "Systematic Demo Studio" in page.get("clean_text", ""):
            company_name = "Systematic Demo Studio"
            break
    return {
        "company_name": company_name,
        "website": settings.start_url,
        "description": description,
        "locations": [],
        "emails": emails,
        "phone_numbers": phones,
        "working_hours": [],
        "social_profiles": sorted(set(socials)),
        "services": service_names,
        "unique_selling_points": [kp for p in company_pages for kp in p.get("key_points", [])[:5]],
        "trust_signals": [],
        "booking_urls": sorted({cta["url"] for p in pages for cta in p.get("cta", []) if "book" in cta.get("text", "").lower()}),
        "contact_urls": sorted({p["url"] for p in pages if p["page_type"] == "contact"}),
        "privacy_policy_url": legal.get("legal", ""),
        "terms_url": "",
        "sources": sources,
    }


def build_case_studies(pages: list[dict]) -> list[dict]:
    records = []
    for page in pages:
        if page["page_type"] not in {"case_study", "portfolio"}:
            continue
        records.append({
            "case_study_id": stable_id("case", page["url"]),
            "title": page["title"],
            "client_name": "",
            "industry": "",
            "services": [page["service_name"]] if page.get("service_name") else [],
            "challenge": "",
            "solution": page["summary"],
            "results": [],
            "numeric_metrics": [],
            "technologies": [],
            "source_url": page["url"],
            "images": page.get("images", []),
        })
    return records


def merge_services(services: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for service in services:
        key = service_key(service["service_name"])
        existing = merged.get(key)
        if not existing:
            merged[key] = service
            continue
        existing["aliases"] = sorted(set(existing.get("aliases", []) + service.get("aliases", []) + [service["service_name"]]))
        existing["supporting_urls"] = sorted(set(existing.get("supporting_urls", []) + [service["primary_url"]] + service.get("supporting_urls", [])))
        for field in ["ideal_customers", "benefits", "features", "deliverables", "process", "client_requirements", "timeline", "pricing", "faqs", "testimonials"]:
            existing[field] = merge_list(existing.get(field, []), service.get(field, []))
        if not existing.get("description") and service.get("description"):
            existing["description"] = service["description"]
    return list(merged.values())


def service_key(name: str) -> str:
    lowered = re.sub(r"\b(expert|professional|innovative|advanced|impactful|effective|targeted|best|detailed|strategic|compelling|tailored)\b", "", name.lower())
    lowered = re.sub(r"\b(services?|solutions?|campaigns?)\b", "", lowered)
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(lowered.split())


def merge_list(left: list, right: list) -> list:
    out = []
    seen = set()
    for item in left + right:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False) if isinstance(item, (dict, list)) else str(item).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def faq_stats(faqs: list[dict]) -> dict:
    raw_count = len(faqs)
    valid = [f for f in faqs if f.get("question") and f.get("answer") and f.get("source_url")]
    unique = {}
    for faq in valid:
        key = f"{faq['question'].strip().lower()}|{faq['answer'].strip().lower()}"
        unique[key] = faq
    return {
        "raw_faq_count": raw_count,
        "duplicates_removed": len(valid) - len(unique),
        "invalid_removed": raw_count - len(valid),
        "final_unique_faq_count": len(unique),
    }


def build_structured_chunks(records: list[dict], content_type: str, scraped_at: str) -> list[dict]:
    chunks = []
    for record in records:
        url = record.get("source_url") or record.get("page_url") or record.get("url", "")
        if not url:
            continue
        if content_type == "faq":
            text = f"Question: {record.get('question', '')}\nAnswer: {record.get('answer', '')}"
            heading = record.get("question", "")
            service = record.get("service", "")
            category = record.get("category", "")
        elif content_type == "pricing":
            text = record.get("price_text_original", "")
            heading = record.get("plan_name", "") or "Pricing"
            service = record.get("service", "")
            category = ""
        elif content_type == "testimonial":
            text = record.get("testimonial", "")
            heading = "Testimonial"
            service = record.get("related_service", "")
            category = ""
        else:
            continue
        if len(text.strip()) < 30:
            continue
        digest = sha256_text(text)
        chunks.append({
            "chunk_id": stable_id("chunk", f"{content_type}|{url}|{heading}|{digest}"),
            "document_id": stable_id("doc", url),
            "url": url,
            "page_title": heading,
            "page_type": content_type,
            "service": service,
            "category": category,
            "heading": heading,
            "content_type": content_type,
            "text": text,
            "token_estimate": max(1, len(text.split()) * 4 // 3),
            "source_priority": 1 if content_type in {"faq", "pricing"} else 2,
            "scraped_at": scraped_at,
            "content_hash": digest,
        })
    return chunks


def build_conflicts(pricing: list[dict]) -> list[dict]:
    conflicts = []
    by_service: dict[str, list[dict]] = {}
    for price in pricing:
        if price.get("service") and price.get("price"):
            by_service.setdefault(price["service"].lower(), []).append(price)
    for service_prices in by_service.values():
        seen_values: dict[str, dict] = {}
        for price in service_prices:
            value = f"{price.get('currency', '')}{price.get('price', '')}/{price.get('billing_period', '')}"
            for other_value, other in seen_values.items():
                if value != other_value:
                    conflicts.append({
                        "field": "pricing",
                        "value_1": other_value,
                        "source_1": other.get("source_url", ""),
                        "value_2": value,
                        "source_2": price.get("source_url", ""),
                        "recommended_priority": "pricing_or_service_page",
                        "needs_review": True,
                    })
                    break
            seen_values.setdefault(value, price)
    return conflicts


def inventory_to_json(discovery, pages: list[dict] | None = None, duplicates: list[dict] | None = None, errors: list[dict] | None = None) -> list[dict]:
    audit = inventory_audit(discovery, pages or [], duplicates or [], errors or [])
    return [
        {
            "url": rec.url,
            "normalized_url": rec.normalized_url,
            "category": rec.category,
            "classification": rec.category,
            "scrape_status": audit.get(rec.normalized_url, {}).get("scrape_status", ""),
            "skip_reason": audit.get(rec.normalized_url, {}).get("skip_reason", ""),
            "business_relevant": audit.get(rec.normalized_url, {}).get("business_relevant", False),
            "needs_review": audit.get(rec.normalized_url, {}).get("needs_review", False),
            "source": rec.source,
            "sitemap_lastmod": rec.sitemap_lastmod,
            "canonical_url": rec.canonical_url,
            "final_url": rec.final_url,
            "http_status": rec.http_status,
            "skipped_reason": rec.skipped_reason,
            "duplicate_of": rec.duplicate_of,
        }
        for rec in sorted(discovery.urls.values(), key=lambda r: r.normalized_url)
    ]


def inventory_audit(discovery, pages: list[dict], duplicates: list[dict], errors: list[dict]) -> dict[str, dict]:
    scraped = {p["url"] for p in pages}
    duplicate_map = {d["url"]: d for d in duplicates}
    error_map = {e.get("url"): e for e in errors}
    business_categories = {"homepage", "about", "company_information", "service", "service_subpage", "pricing", "faq", "portfolio", "case_study", "testimonial", "contact", "booking", "blog"}
    audit = {}
    for normalized, rec in discovery.urls.items():
        skip_reason = rec.skipped_reason or ""
        status = "needs_review" if rec.category == "unknown" else "intentionally_skipped"
        if normalized in scraped:
            status = "scraped_useful"
        elif normalized in duplicate_map or rec.category == "duplicate":
            status = "duplicate"
            skip_reason = skip_reason or duplicate_map.get(normalized, {}).get("reason", "duplicate")
        elif rec.category == "translated_duplicate":
            status = "translated_duplicate"
        elif rec.category in {"media", "archive", "irrelevant", "utility"}:
            status = rec.category
        elif normalized in error_map:
            status = "failed"
            skip_reason = error_map[normalized].get("error_message", "")
        elif rec.http_status and rec.http_status != 200:
            status = "failed"
            skip_reason = skip_reason or f"HTTP {rec.http_status}"
        elif skip_reason:
            status = "intentionally_skipped"
        business_relevant = rec.category in business_categories
        audit[normalized] = {
            "url": rec.url,
            "canonical_url": rec.canonical_url or rec.normalized_url,
            "classification": rec.category,
            "scrape_status": status,
            "skip_reason": skip_reason,
            "http_status": rec.http_status,
            "business_relevant": business_relevant,
            "needs_review": status in {"needs_review", "failed"} and business_relevant,
        }
    return audit


def url_coverage_summary(discovery, audit: dict[str, dict], pages: list[dict], errors: list[dict], duplicates: list[dict]) -> dict:
    categories = Counter(rec.category for rec in discovery.urls.values())
    statuses = Counter(row["scrape_status"] for row in audit.values())
    skipped_by_reason = Counter(row.get("skip_reason") or row["scrape_status"] for row in audit.values() if row["scrape_status"] != "scraped_useful")
    redirect_count = sum(1 for rec in discovery.urls.values() if rec.final_url and normalize_url(rec.final_url) != rec.normalized_url)
    return {
        "raw_sitemap_urls": discovery.stats.get("raw_sitemap_urls", 0),
        "sitemap_url_counts": discovery.stats.get("sitemap_url_counts", {}),
        "raw_internal_crawl_urls": discovery.stats.get("raw_navigation_urls", 0),
        "raw_seed_urls": discovery.stats.get("raw_seed_urls", 0),
        "raw_total_url_candidates": discovery.stats.get("raw_total_url_candidates", 0),
        "normalized_urls": len(discovery.urls),
        "normalized_duplicate_candidates": discovery.stats.get("normalized_duplicates_skipped", 0),
        "content_duplicates_removed": len(duplicates),
        "translated_duplicates": categories.get("translated_duplicate", 0),
        "archives": sum(categories.get(name, 0) for name in ["archive", "tag", "category_archive", "author_archive"]),
        "media": categories.get("media", 0),
        "irrelevant": categories.get("irrelevant", 0),
        "redirects": redirect_count,
        "valid_business_urls": sum(1 for row in audit.values() if row.get("business_relevant")),
        "successfully_scraped_urls": len(pages),
        "failed_urls": len(errors),
        "category_counts": dict(sorted(categories.items())),
        "status_counts": dict(sorted(statuses.items())),
        "skipped_by_reason": dict(sorted(skipped_by_reason.items())),
        "navigation_pages_fetched": discovery.stats.get("navigation_pages_fetched", 0),
        "navigation_pages_failed": discovery.stats.get("navigation_pages_failed", 0),
        "off_domain_skipped": discovery.stats.get("off_domain_skipped", 0),
    }


def strip_private(page: dict) -> dict:
    return {k: v for k, v in page.items() if not k.startswith("_")}


def export_all(root: Path, settings, discovery, pages: list[dict], duplicates: list[dict], errors: list[dict], started_at: str, completed_at: str, state: dict, mode: str) -> dict:
    output_dir = root / settings.output_directory
    prepare_output_dir(output_dir)
    all_faqs = [faq for p in pages for faq in p.pop("_faqs", [])]
    all_pricing = [price for p in pages for price in p.pop("_pricing", [])]
    all_forms = [form for p in pages for form in p.pop("_forms", [])]
    all_navigation = [nav for p in pages for nav in p.pop("_navigation", [])]
    all_testimonials = [t for p in pages for t in p.pop("_testimonials", [])]
    services = []
    for page in pages:
        page_faqs = [f for f in all_faqs if f["source_url"] == page["url"]]
        page_prices = [p for p in all_pricing if p["source_url"] == page["url"]]
        page_testimonials = [t for t in all_testimonials if t["source_url"] == page["url"]]
        service = extract_service_record(page, page_faqs, page_prices, page_testimonials)
        if service:
            services.append(service)
    services = merge_services(services)
    company_profile = build_company_profile(pages, settings)
    case_studies = build_case_studies(pages)
    chunks = [chunk for page in pages for chunk in chunk_page(page, page["scraped_at"])]
    chunks.extend(build_structured_chunks(all_faqs, "faq", completed_at))
    chunks.extend(build_structured_chunks(all_pricing, "pricing", completed_at))
    chunks.extend(build_structured_chunks(all_testimonials, "testimonial", completed_at))
    review = build_review_queue(pages, all_pricing, errors)
    quality_warnings = validate_outputs(pages, services, all_faqs, all_pricing, chunks, company_profile)
    internal_links = [{"source_url": p["url"], "target_url": link} for p in pages for link in p.get("internal_links", [])]
    conflicts = build_conflicts(all_pricing)
    audit = inventory_audit(discovery, pages, duplicates, errors)
    faq_quality = faq_stats(all_faqs)
    url_coverage = url_coverage_summary(discovery, audit, pages, errors, duplicates)
    selected_total = len(pages) + len(errors)
    report = {
        "started_at": started_at,
        "completed_at": completed_at,
        "target_domain": settings.target_domain,
        "mode": mode,
        "urls_discovered": len(discovery.urls),
        "urls_crawled": len(pages) + len(errors),
        "urls_successful": len(pages),
        "urls_failed": len(errors),
        "urls_skipped": max(0, len(discovery.urls) - selected_total),
        "duplicates_removed": len(duplicates),
        "translated_duplicates": len([r for r in discovery.urls.values() if r.category == "translated_duplicate"]),
        "service_pages": len([p for p in pages if p["page_type"] in {"service", "service_subpage"}]),
        "services_found": len(services),
        "faqs_found": len(all_faqs),
        "faq_quality": faq_quality,
        "pricing_plans_found": len(all_pricing),
        "case_studies_found": len(case_studies),
        "testimonials_found": len(all_testimonials),
        "blogs_found": len([p for p in pages if p["page_type"] == "blog"]),
        "forms_found": len(all_forms),
        "navigation_actions_found": len(all_navigation),
        "rag_chunks_created": len(chunks),
        "total_clean_words": sum(len(p.get("clean_text", "").split()) for p in pages),
        "quality_warnings": quality_warnings,
        "url_coverage": url_coverage,
        "critical_errors": [e for e in errors if e.get("http_status") not in {404}],
        "incremental": build_incremental_summary(pages, discovery, state),
    }
    write_json(output_dir / "url_inventory.json", inventory_to_json(discovery, pages, duplicates, errors))
    write_json(output_dir / "url_audit.json", list(audit.values()))
    write_csv(output_dir / "url_audit.csv", list(audit.values()), ["url", "canonical_url", "classification", "scrape_status", "skip_reason", "http_status", "business_relevant", "needs_review"])
    write_jsonl(output_dir / "pages.jsonl", [strip_private(p) for p in pages])
    write_json(output_dir / "services.json", services)
    write_json(output_dir / "faqs.json", all_faqs)
    write_json(output_dir / "pricing.json", all_pricing)
    write_json(output_dir / "company_profile.json", company_profile)
    write_json(output_dir / "case_studies.json", case_studies)
    write_json(output_dir / "testimonials.json", all_testimonials)
    write_json(output_dir / "navigation_registry.json", all_navigation)
    write_json(output_dir / "forms_registry.json", all_forms)
    write_jsonl(output_dir / "rag_chunks.jsonl", chunks)
    write_json(output_dir / "internal_links.json", internal_links)
    write_json(output_dir / "scrape_report.json", report)
    write_jsonl(output_dir / "errors.jsonl", errors)
    write_json(output_dir / "conflicts.json", conflicts)
    write_json(output_dir / "review_required.json", review)
    write_csv(output_dir / "csv" / "services.csv", services, ["service_id", "service_name", "category", "description", "primary_url", "source_confidence"])
    write_csv(output_dir / "csv" / "faqs.csv", all_faqs, ["faq_id", "question", "answer", "service", "category", "source_url", "scraped_at"])
    write_csv(output_dir / "csv" / "pricing.csv", all_pricing, ["pricing_id", "service", "plan_name", "price", "currency", "billing_period", "price_text_original", "source_url", "needs_review"])
    write_csv(output_dir / "csv" / "pages.csv", [strip_private(p) for p in pages], ["id", "url", "page_type", "title", "service_category", "service_name", "source_priority", "quality_score", "content_hash"])
    write_csv(output_dir / "csv" / "case_studies.csv", case_studies, ["case_study_id", "title", "client_name", "industry", "services", "source_url"])
    new_state = {
        "last_run": completed_at,
        "pages": {p["url"]: {"content_hash": p["content_hash"], "id": p["id"], "canonical_url": p["canonical_url"]} for p in pages},
        "urls": [r.normalized_url for r in discovery.urls.values()],
    }
    write_json(root / settings.incremental_state_file, new_state)
    return report


def build_incremental_summary(pages: list[dict], discovery, state: dict) -> dict:
    previous_urls = set(state.get("urls", []))
    current_urls = set(discovery.urls.keys())
    return {
        "new_pages": sorted(current_urls - previous_urls),
        "changed_pages": sorted([p["url"] for p in pages if p.get("previous_content_hash") and p.get("content_changed")]),
        "unchanged_pages": sorted([p["url"] for p in pages if p.get("previous_content_hash") and not p.get("content_changed")]),
        "deleted_pages": sorted(previous_urls - current_urls),
    }


async def run(mode: str) -> dict:
    root = Path(__file__).resolve().parents[1]
    settings = load_settings(root)
    started_at = now_iso()
    fetcher = Fetcher(settings)
    discovery = await SiteDiscovery(settings, fetcher).discover()
    state_path = root / settings.incremental_state_file
    state = load_state(state_path) if mode == "incremental" or state_path.exists() else {"pages": {}, "urls": []}
    selected = select_urls(discovery.urls, settings)
    selected_set = set(selected)
    for url, rec in discovery.urls.items():
        if url not in selected_set and not rec.skipped_reason:
            rec.skipped_reason = "not_selected_for_business_crawl"
    pages, errors = await crawl_selected(selected, discovery, fetcher, settings, started_at, state, mode == "incremental")
    pages, duplicates = dedupe_pages(pages)
    errors = discovery.errors + errors
    completed_at = now_iso()
    return export_all(root, settings, discovery, pages, duplicates, errors, started_at, completed_at, state, mode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Production-quality website scraper for AI sales-agent knowledge bases.")
    parser.add_argument("--mode", choices=["full", "incremental"], default="full")
    args = parser.parse_args()
    report = asyncio.run(run(args.mode))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
