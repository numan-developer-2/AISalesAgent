from __future__ import annotations

import re

from src.utils.url import classify_url


SERVICE_KEYWORDS = {
    "SEO": [
        "seo",
        "search engine optimization",
        "local seo",
        "gmb",
        "google business profile",
        "technical seo",
        "link building",
        "shopify seo",
        "seo audit",
        "website seo",
        "pr outreach",
    ],
    "Development": [
        "web design",
        "website development",
        "wordpress",
        "wordpress development",
        "shopify development",
        "shopify website",
        "e-commerce",
        "ecommerce",
        "web application",
        "web app",
        "mobile application",
        "mobile app",
        "crm",
        "product development",
    ],
    "Digital Marketing": [
        "digital marketing",
        "ppc",
        "paid advertising",
        "advertisement",
        "advertising",
        "google ads",
        "meta ads",
        "search engine marketing",
        "social media",
        "content marketing",
        "content writing",
        "copywriting",
        "seo writing",
        "email marketing",
        "influencer",
        "affiliate",
        "lead generation",
    ],
    "Design / Branding": ["graphic design", "ui/ux", "ui ux", "branding", "logo design", "designing"],
}


SERVICE_NAME_PATTERNS = [
    (r"seo-writing|seo writing", "SEO Writing"),
    (r"copywriting", "Copywriting"),
    (r"shopify-seo|shopify seo", "Shopify SEO"),
    (r"local-seo|local seo", "Local SEO"),
    (r"google-business|gmb|google business profile", "Google Business Profile Optimization"),
    (r"technical-seo|technical seo", "Technical SEO"),
    (r"website-seo|website seo", "Website SEO"),
    (r"seo-audits?|seo audits?", "SEO Audits"),
    (r"link-building|link building", "Link Building"),
    (r"pr-outreach|pr outreach", "PR Outreach"),
    (r"web-design|web design", "Web Design"),
    (r"website-development|website development", "Website Development"),
    (r"wordpress", "WordPress Development"),
    (r"shopify-website|shopify development|shopify website", "Shopify Development"),
    (r"e-?commerce", "E-commerce Development"),
    (r"web-apps?|web applications?", "Web Applications"),
    (r"mobile-apps?|mobile applications?", "Mobile Applications"),
    (r"crm-development|crm", "CRM Development"),
    (r"product-development|product development", "Product Development"),
    (r"(^|/)marketing/?$|digital-marketing|marketing services", "Digital Marketing"),
    (r"(^|/)development/?$|development services", "Development Services"),
    (r"(^|/)seo/?$|seo services", "SEO Services"),
    (r"advertisments|advertisements$|digital advertising", "Digital Advertising"),
    (r"google-ads|ppc|paid advertising|search engine marketing", "Google Ads"),
    (r"meta-ads", "Meta Ads"),
    (r"social-media-ads", "Social Media Ads"),
    (r"social-media-marketing|social media marketing", "Social Media Marketing"),
    (r"content-marketing|content marketing", "Content Marketing"),
    (r"content-writing|content writing", "Content Writing"),
    (r"email-marketing|email marketing", "Email Marketing"),
    (r"influencer-marketing|influencer", "Influencer Marketing"),
    (r"affiliate-marketing|affiliate", "Affiliate Marketing"),
    (r"lead-generation|lead generation", "Lead Generation"),
    (r"graphic-design|graphic design", "Graphic Design"),
    (r"ui-ux|ui ux", "UI/UX Design"),
    (r"logo-design|logo design", "Logo Design"),
    (r"designing|design services", "Design Services"),
]


def classify_page(url: str, title: str, text: str) -> tuple[str, str, str]:
    url_type = classify_url(url)
    strong_haystack = f"{url} {title}".lower()
    haystack = f"{strong_haystack} {text[:2000]}".lower()
    if url_type in {"service", "service_subpage", "pricing", "faq", "portfolio", "case_study", "testimonial", "about", "contact", "booking", "blog", "homepage", "legal"}:
        page_type = url_type
    else:
        page_type = "unknown"
    if re.search(r"\bportfolio|our work|case stud", title, re.I):
        page_type = "portfolio"
    category = ""
    service_name = ""
    for service_category, keywords in SERVICE_KEYWORDS.items():
        if any(kw in strong_haystack for kw in keywords):
            category = service_category
            break
    if not category:
        for service_category, keywords in SERVICE_KEYWORDS.items():
            if any(kw in haystack for kw in keywords):
                category = service_category
                break
    if category and page_type == "unknown":
        page_type = "service"
    if page_type in {"service", "service_subpage", "pricing"}:
        service_name = normalize_service_name(url, title, text)
        category = category_for_service(service_name) or category
    if page_type == "homepage":
        category = "company_information"
    if page_type == "about":
        category = "company_information"
    if page_type == "contact":
        category = "company_information"
    return page_type, category, service_name


def normalize_service_name(url: str, title: str, text: str = "") -> str:
    haystack = f"{url} {title}".lower()
    for pattern, service_name in SERVICE_NAME_PATTERNS:
        if re.search(pattern, haystack):
            return service_name
    cleaned = re.sub(r"\s+-\s+systematic demo studio\s*$", "", title or "", flags=re.I).strip()
    cleaned = re.sub(r"\b(expert|professional|innovative|advanced|impactful|effective|targeted|best|detailed|strategic|compelling|tailored)\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
    return cleaned or title.strip()


def category_for_service(service_name: str) -> str:
    lowered = service_name.lower()
    if any(term in lowered for term in ["seo", "link building", "pr outreach", "google business profile"]):
        return "SEO"
    if any(term in lowered for term in ["development", "applications", "shopify", "e-commerce", "web design", "crm"]):
        return "Development"
    if any(term in lowered for term in ["marketing", "ads", "advertising", "copywriting", "content writing", "email", "influencer", "affiliate", "lead generation"]):
        return "Digital Marketing"
    if any(term in lowered for term in ["design", "branding", "logo", "ui/ux"]):
        return "Design / Branding"
    return ""


def source_priority(page_type: str) -> int:
    if page_type in {"pricing", "service", "service_subpage", "homepage", "about", "faq", "contact", "booking"}:
        return 1
    if page_type in {"case_study", "portfolio", "testimonial"}:
        return 2
    if page_type == "blog":
        return 3
    return 4


def sales_intents(page_type: str, text: str) -> list[str]:
    intents = set()
    lowered = text.lower()
    if page_type in {"service", "service_subpage", "homepage"}:
        intents.add("service_discovery")
    if re.search(r"(\$|usd|pkr|price|pricing|package|plan|month)", lowered):
        intents.add("pricing_inquiry")
    if re.search(r"(timeline|weeks|months|days|process|deliver)", lowered):
        intents.add("timeline_inquiry")
    if page_type in {"portfolio", "case_study"}:
        intents.add("portfolio_request")
    if page_type in {"contact", "booking"} or re.search(r"(contact|book|consultation|quote|proposal)", lowered):
        intents.add("proposal_request")
    return sorted(intents)


def customer_questions(page_type: str, service_name: str, text: str) -> list[str]:
    questions = set()
    if page_type in {"homepage", "service", "service_subpage"}:
        questions.add("What services do you offer?")
    if service_name:
        questions.add(f"What is included in {service_name}?")
    if "price" in text.lower() or "package" in text.lower():
        questions.add("How much does this service cost?")
    if "contact" in text.lower() or "quote" in text.lower():
        questions.add("How can I contact the company?")
    if "portfolio" in text.lower() or "case" in text.lower():
        questions.add("Can I see examples of previous work?")
    return sorted(questions)
