from __future__ import annotations

import re
from bs4 import BeautifulSoup, Tag


DROP_SELECTORS = [
    "script",
    "style",
    "noscript",
    "svg",
    "iframe",
    "canvas",
    "header",
    "footer",
    "nav",
    "aside",
    ".elementor-location-header",
    ".elementor-location-footer",
    ".cookie",
    ".cookies",
    ".newsletter",
    ".share",
    ".social-share",
]


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "")
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    return text.strip()


def strip_boilerplate(soup: BeautifulSoup) -> BeautifulSoup:
    cloned = BeautifulSoup(str(soup), "lxml")
    for selector in DROP_SELECTORS:
        for node in cloned.select(selector):
            node.decompose()
    for node in cloned.find_all(attrs={"aria-hidden": "true"}):
        node.decompose()
    return cloned


def main_content_soup(soup: BeautifulSoup) -> BeautifulSoup | Tag:
    for selector in ["main", "article", "[role=main]", ".site-main", ".entry-content", ".page-content", ".elementor"]:
        node = soup.select_one(selector)
        if node and clean_text(node.get_text(" ", strip=True)):
            return node
    return soup.body or soup


def extract_clean_text(soup: BeautifulSoup) -> str:
    stripped = strip_boilerplate(soup)
    main = main_content_soup(stripped)
    lines = []
    for element in main.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th", "blockquote"], recursive=True):
        text = clean_text(element.get_text(" ", strip=True))
        if text and len(text) > 1:
            lines.append(text)
    deduped = []
    seen = set()
    for line in lines:
        key = line.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(line)
    return "\n".join(deduped)
