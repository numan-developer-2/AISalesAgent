from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from src.config import Settings
from src.crawler.fetcher import Fetcher
from src.utils.url import classify_url, normalize_url, same_domain, should_exclude


@dataclass
class DiscoveredUrl:
    url: str
    normalized_url: str
    category: str
    source: str
    sitemap_lastmod: str = ""
    canonical_url: str = ""
    final_url: str = ""
    http_status: int | None = None
    skipped_reason: str = ""
    duplicate_of: str = ""


@dataclass
class DiscoveryResult:
    urls: dict[str, DiscoveredUrl] = field(default_factory=dict)
    robots_txt: str = ""
    sitemaps: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def parse_sitemap_xml(xml_text: str) -> tuple[list[str], list[tuple[str, str]]]:
    root = ET.fromstring(xml_text.encode("utf-8"))
    sitemaps: list[str] = []
    urls: list[tuple[str, str]] = []
    for sitemap in root.findall(".//sm:sitemap", SITEMAP_NS):
        loc = sitemap.findtext("sm:loc", default="", namespaces=SITEMAP_NS).strip()
        if loc:
            sitemaps.append(loc)
    for url_node in root.findall(".//sm:url", SITEMAP_NS):
        loc = url_node.findtext("sm:loc", default="", namespaces=SITEMAP_NS).strip()
        lastmod = url_node.findtext("sm:lastmod", default="", namespaces=SITEMAP_NS).strip()
        if loc:
            urls.append((loc, lastmod))
    return sitemaps, urls


class SiteDiscovery:
    def __init__(self, settings: Settings, fetcher: Fetcher):
        self.settings = settings
        self.fetcher = fetcher

    async def discover(self) -> DiscoveryResult:
        result = DiscoveryResult(stats={
            "raw_sitemap_urls": 0,
            "raw_navigation_urls": 0,
            "raw_seed_urls": 0,
            "raw_total_url_candidates": 0,
            "normalized_duplicates_skipped": 0,
            "off_domain_skipped": 0,
            "sitemap_url_counts": {},
            "navigation_pages_fetched": 0,
            "navigation_pages_failed": 0,
        })
        robots_url = urljoin(self.settings.start_url, "/robots.txt")
        robots = await self.fetcher.fetch(robots_url)
        result.robots_txt = robots.content
        sitemap_urls = self._sitemaps_from_robots(robots.content) or [urljoin(self.settings.start_url, "/sitemap.xml"), urljoin(self.settings.start_url, "/sitemap_index.xml")]
        seen_sitemaps: set[str] = set()
        queue = [normalize_url(u) for u in sitemap_urls]
        while queue:
            sitemap_url = queue.pop(0)
            if sitemap_url in seen_sitemaps:
                continue
            seen_sitemaps.add(sitemap_url)
            sitemap = await self.fetcher.fetch(sitemap_url)
            if sitemap.status_code != 200 or not sitemap.content:
                result.errors.append(self._error_record(sitemap_url, sitemap))
                continue
            result.sitemaps.append(sitemap_url)
            try:
                child_sitemaps, urls = parse_sitemap_xml(sitemap.content)
            except Exception as exc:
                result.errors.append({"url": sitemap_url, "error_type": "sitemap_parse_error", "error_message": str(exc), "http_status": sitemap.status_code, "retry_count": sitemap.retry_count})
                continue
            result.stats["sitemap_url_counts"][sitemap_url] = len(urls)
            result.stats["raw_sitemap_urls"] += len(urls)
            result.stats["raw_total_url_candidates"] += len(urls)
            queue.extend(normalize_url(u) for u in child_sitemaps if same_domain(u, self.settings.target_domain))
            for raw_url, lastmod in urls:
                self._add_url(result, raw_url, "sitemap", lastmod)
        result.stats["raw_seed_urls"] += 1
        result.stats["raw_total_url_candidates"] += 1
        self._add_url(result, self.settings.start_url, "seed")
        await self._navigation_discovery(result)
        self._mark_duplicates(result)
        return result

    def _sitemaps_from_robots(self, robots_text: str) -> list[str]:
        return [line.split(":", 1)[1].strip() for line in robots_text.splitlines() if line.lower().startswith("sitemap:")]

    def _add_url(self, result: DiscoveryResult, raw_url: str, source: str, lastmod: str = "") -> None:
        normalized = normalize_url(raw_url)
        if not same_domain(normalized, self.settings.target_domain):
            result.stats["off_domain_skipped"] = result.stats.get("off_domain_skipped", 0) + 1
            return
        category = classify_url(normalized)
        if should_exclude(normalized, self.settings.exclude_patterns):
            category = "irrelevant"
        existing = result.urls.get(normalized)
        if existing:
            result.stats["normalized_duplicates_skipped"] = result.stats.get("normalized_duplicates_skipped", 0) + 1
            if lastmod and not existing.sitemap_lastmod:
                existing.sitemap_lastmod = lastmod
            return
        result.urls[normalized] = DiscoveredUrl(url=raw_url, normalized_url=normalized, category=category, source=source, sitemap_lastmod=lastmod)

    async def _navigation_discovery(self, result: DiscoveryResult) -> None:
        seeds = [self.settings.start_url]
        seeds.extend(
            u for u, rec in sorted(result.urls.items())
            if rec.category not in {"media", "irrelevant", "archive", "tag", "category_archive", "author_archive", "utility"}
        )
        for url in dict.fromkeys(seeds):
            fetched = await self.fetcher.fetch(url)
            if fetched.status_code != 200 or not fetched.content:
                result.stats["navigation_pages_failed"] = result.stats.get("navigation_pages_failed", 0) + 1
                continue
            result.stats["navigation_pages_fetched"] = result.stats.get("navigation_pages_fetched", 0) + 1
            soup = BeautifulSoup(fetched.content, "lxml")
            canonical = self._canonical(soup, url)
            if canonical:
                normalized = normalize_url(url)
                if normalized in result.urls:
                    result.urls[normalized].canonical_url = normalize_url(canonical)
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                    continue
                result.stats["raw_navigation_urls"] = result.stats.get("raw_navigation_urls", 0) + 1
                result.stats["raw_total_url_candidates"] = result.stats.get("raw_total_url_candidates", 0) + 1
                self._add_url(result, urljoin(url, href), "navigation")

    def _canonical(self, soup: BeautifulSoup, url: str) -> str:
        tag = soup.find("link", rel=lambda value: value and "canonical" in value)
        return urljoin(url, tag.get("href", "")) if tag and tag.get("href") else ""

    def _mark_duplicates(self, result: DiscoveryResult) -> None:
        canonical_seen: dict[str, str] = {}
        for normalized, rec in result.urls.items():
            canonical = normalize_url(rec.canonical_url or normalized)
            if canonical in canonical_seen and canonical_seen[canonical] != normalized:
                rec.category = "duplicate"
                rec.duplicate_of = canonical_seen[canonical]
            else:
                canonical_seen[canonical] = normalized
            if re.search(r"/(es|fr|de|ar|ur|hi|zh|tr|nl|it|pt|ru)(/|$)", urlparse(normalized).path.lower()):
                rec.category = "translated_duplicate"

    def _error_record(self, url: str, fetched) -> dict:
        return {
            "url": url,
            "timestamp": "",
            "http_status": fetched.status_code,
            "error_type": "fetch_error",
            "error_message": fetched.error or f"HTTP {fetched.status_code}",
            "retry_count": fetched.retry_count,
        }
