from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "gclid",
    "fbclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
}


@dataclass(frozen=True)
class UrlInfo:
    url: str
    normalized_url: str
    category: str
    reason: str


def normalize_url(url: str, base_url: str | None = None, keep_query: bool = True) -> str:
    absolute = urljoin(base_url or "", (url or "").strip())
    parsed = urlparse(absolute)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = re.sub(r"/+", "/", parsed.path or "/")
    path = posixpath.normpath(path)
    if parsed.path.endswith("/") and not path.endswith("/"):
        path += "/"
    if path == ".":
        path = "/"
    if not path.startswith("/"):
        path = "/" + path
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    query = ""
    if keep_query and parsed.query:
        params = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=False) if k.lower() not in TRACKING_PARAMS]
        query = urlencode(sorted(params))
    return urlunparse((scheme, netloc, path, "", query, ""))


def same_domain(url: str, target_domain: str) -> bool:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host == target_domain.lower().removeprefix("www.")


def classify_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/").lower()
    if not path:
        return "homepage"
    if re.search(r"\.(jpg|jpeg|png|gif|webp|svg|pdf|zip|mp4|mp3|css|js)$", path):
        return "media"
    if "/tag/" in f"/{path}/":
        return "tag"
    if "/category/" in f"/{path}/":
        return "category_archive"
    if "/author/" in f"/{path}/":
        return "author_archive"
    if re.search(r"(^|/)page(/\d+)?$", path):
        return "archive"
    if any(x in path for x in ["privacy", "terms", "refund", "cookie"]):
        return "legal"
    if any(x in path for x in ["contact", "get-in-touch"]):
        return "contact"
    if any(x in path for x in ["booking", "appointment", "consultation", "schedule"]):
        return "booking"
    if any(x in path for x in ["pricing", "packages", "plans"]):
        return "pricing"
    if "faq" in path:
        return "faq"
    if any(x in path for x in ["portfolio", "work", "project"]):
        return "portfolio"
    if any(x in path for x in ["case-study", "case-studies", "success-story"]):
        return "case_study"
    if any(x in path for x in ["testimonial", "reviews"]):
        return "testimonial"
    if any(x in path for x in ["about", "company", "who-we-are"]):
        return "about"
    if any(x in path for x in ["blog", "article", "news"]):
        return "blog"
    service_terms = [
        "seo",
        "gmb",
        "google-business",
        "google-ads",
        "meta-ads",
        "marketing",
        "ppc",
        "advertising",
        "advertisements",
        "advertisments",
        "ads",
        "search-engine-marketing",
        "social-media",
        "content",
        "email",
        "influencer",
        "affiliate",
        "lead-generation",
        "product-development",
        "ui-ux",
        "web-design",
        "website",
        "wordpress",
        "shopify",
        "ecommerce",
        "e-commerce",
        "development",
        "application",
        "mobile-app",
        "crm",
        "branding",
        "logo",
        "graphic",
    ]
    if path == "services":
        return "service"
    if path.startswith(("service/", "services/")):
        return "service_subpage" if "/" in path else "service"
    if any(term in path for term in service_terms):
        return "service"
    if any(x in path for x in ["sitemap", "thank-you", "search"]):
        return "utility"
    return "unknown"


def should_exclude(url: str, patterns: Iterable[str]) -> bool:
    lowered = url.lower()
    return any(pattern.lower() in lowered for pattern in patterns if pattern)
