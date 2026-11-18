from __future__ import annotations

import json
import re
from urllib.parse import unquote
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from src.cleaners.html_cleaner import clean_text, extract_clean_text
from src.utils.hashing import stable_id
from src.utils.url import normalize_url, same_domain


EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:(?:\+|00)\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}")
PRICE_RE = re.compile(
    r"(?P<currency>\$|USD|PKR|GBP|EUR|\u00a3|\u20ac)\s?(?P<amount>\d[\d,]*(?:\.\d+)?)"
    r"|(?P<amount2>\d[\d,]*(?:\.\d+)?)\s?(?P<currency2>USD|PKR|GBP|EUR|dollars?|rupees?)",
    re.I,
)
PRICING_CONTEXT_RE = re.compile(r"(\$|usd|pkr|gbp|eur|\u00a3|\u20ac|price|pricing|package|plan|month|monthly|year|yearly|starting|from|quote)", re.I)
FORM_FIELD_SKIP_TYPES = {"hidden", "submit", "button", "reset", "image"}


def soup_from_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "lxml")


def title_and_meta(soup: BeautifulSoup) -> tuple[str, str, str]:
    title = clean_text((soup.find("title").get_text(" ", strip=True) if soup.find("title") else ""))
    h1 = soup.find("h1")
    if h1 and clean_text(h1.get_text(" ", strip=True)):
        title = clean_text(h1.get_text(" ", strip=True))
    meta = soup.find("meta", attrs={"name": "description"})
    description = clean_text(meta.get("content", "")) if meta else ""
    html = soup.find("html")
    lang = html.get("lang", "en").split("-")[0] if html else "en"
    return title, description, lang or "en"


def canonical_url(soup: BeautifulSoup, url: str) -> str:
    tag = soup.find("link", rel=lambda value: value and "canonical" in value)
    return normalize_url(urljoin(url, tag.get("href", ""))) if tag and tag.get("href") else normalize_url(url)


def headings(soup: BeautifulSoup) -> list[dict]:
    result = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        text = clean_text(tag.get_text(" ", strip=True))
        if text:
            result.append({"level": tag.name, "text": text})
    return result


def links(soup: BeautifulSoup, url: str, target_domain: str) -> tuple[list[str], list[str]]:
    internal, external = [], []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        normalized = normalize_url(urljoin(url, href))
        if same_domain(normalized, target_domain):
            internal.append(normalized)
        else:
            external.append(normalized)
    return sorted(set(internal)), sorted(set(external))


def images(soup: BeautifulSoup, url: str) -> list[dict]:
    out = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src:
            continue
        image_url = normalize_url(urljoin(url, src), keep_query=False)
        alt = clean_text(img.get("alt", ""))
        lowered = f"{image_url} {alt}".lower()
        if "accessibility-onetap" in lowered or re.search(r"\b(flag|toggle icon|language)\b", lowered):
            continue
        out.append({"url": image_url, "alt": alt})
    return out


def extract_json_ld(soup: BeautifulSoup) -> list[dict]:
    records = []
    for script in soup.find_all("script", type=lambda value: value and "ld+json" in value):
        try:
            payload = json.loads(script.string or script.get_text())
        except Exception:
            continue
        if isinstance(payload, list):
            records.extend([x for x in payload if isinstance(x, dict)])
        elif isinstance(payload, dict):
            graph = payload.get("@graph")
            if isinstance(graph, list):
                records.extend([x for x in graph if isinstance(x, dict)])
            else:
                records.append(payload)
    return records


def extract_faqs(soup: BeautifulSoup, url: str, service: str, category: str, source_heading: str, scraped_at: str) -> list[dict]:
    faqs: list[dict] = []
    for item in extract_json_ld(soup):
        item_type = item.get("@type")
        if item_type == "FAQPage":
            for idx, entity in enumerate(item.get("mainEntity", []) or []):
                q = clean_text(entity.get("name", ""))
                accepted = entity.get("acceptedAnswer", {}) or {}
                a = clean_text(BeautifulSoup(accepted.get("text", ""), "lxml").get_text(" ", strip=True))
                if q and a:
                    faqs.append(_faq_record(q, a, service, category, url, source_heading, idx, scraped_at))
    faq_like = soup.select(".faq, .faqs, .accordion, .elementor-accordion, details, [class*=faq], [class*=accordion]")
    idx = len(faqs)
    for container in faq_like:
        questions = container.find_all(["h2", "h3", "h4", "summary", "button"])
        for q_node in questions:
            q = clean_text(q_node.get_text(" ", strip=True))
            if not q or "?" not in q:
                continue
            answer_parts = []
            sibling = q_node.find_next_sibling()
            scan_count = 0
            while sibling and scan_count < 4:
                if isinstance(sibling, Tag):
                    if sibling.name in {"h2", "h3", "h4", "summary", "button"}:
                        break
                    text = clean_text(sibling.get_text(" ", strip=True))
                    if text:
                        answer_parts.append(text)
                sibling = sibling.find_next_sibling()
                scan_count += 1
            a = clean_text(" ".join(answer_parts))
            if q and a:
                faqs.append(_faq_record(q, a, service, category, url, source_heading, idx, scraped_at))
                idx += 1
    deduped: dict[str, dict] = {}
    for faq in faqs:
        key = f"{faq['question'].lower()}|{faq['answer'].lower()}"
        deduped[key] = faq
    return list(deduped.values())


def _faq_record(question: str, answer: str, service: str, category: str, url: str, source_heading: str, position: int, scraped_at: str) -> dict:
    return {
        "faq_id": stable_id("faq", f"{url}|{question}|{answer}"),
        "question": question,
        "answer": answer,
        "service": service,
        "category": category,
        "source_url": url,
        "source_heading": source_heading,
        "faq_position": position,
        "scraped_at": scraped_at,
    }


def extract_pricing(soup: BeautifulSoup, url: str, service: str, scraped_at: str) -> list[dict]:
    records: list[dict] = []
    visible_soup = BeautifulSoup(str(soup.body or soup), "lxml")
    for node in visible_soup.find_all(["script", "style", "noscript", "svg", "head"]):
        node.decompose()
    candidates = visible_soup.find_all(string=PRICE_RE)
    for idx, text_node in enumerate(candidates):
        if text_node.parent and text_node.parent.name in {"script", "style", "noscript", "svg", "head"}:
            continue
        text = clean_text(str(text_node))
        if any(noise in text.lower() for noise in ["language", "ajax", "nonce", "wp-admin", "elementor", "fontawesome"]):
            continue
        match = PRICE_RE.search(text)
        if not match:
            continue
        card = text_node.find_parent(["section", "div", "li", "tr", "article"]) if hasattr(text_node, "find_parent") else None
        card_text = clean_text(card.get_text(" ", strip=True)) if card else text
        if any(noise in card_text.lower() for noise in ["language", "ajax", "nonce", "wp-admin", "elementor", "fontawesome"]):
            continue
        if not re.search(r"(\$|usd|pkr|gbp|eur|£|€|price|pricing|package|plan|month|monthly|starting|from)", card_text, re.I):
            continue
        plan_name = ""
        if card:
            heading = card.find(["h2", "h3", "h4", "strong"])
            plan_name = clean_text(heading.get_text(" ", strip=True)) if heading else ""
        features = []
        if card:
            features = [clean_text(li.get_text(" ", strip=True)) for li in card.find_all("li") if clean_text(li.get_text(" ", strip=True))]
        cta_text, cta_url = "", ""
        if card:
            a = card.find("a", href=True)
            if a:
                cta_text = clean_text(a.get_text(" ", strip=True))
                cta_url = normalize_url(urljoin(url, a["href"]))
        currency = match.group("currency") or match.group("currency2") or ""
        price = match.group("amount") or match.group("amount2") or None
        records.append({
            "pricing_id": stable_id("price", f"{url}|{idx}|{card_text[:100]}"),
            "service": service,
            "plan_name": plan_name,
            "price": price,
            "currency": currency,
            "billing_period": "monthly" if re.search(r"/\s?mo|month|monthly", card_text, re.I) else "",
            "starting_from": bool(re.search(r"start|from|starting", card_text, re.I)),
            "price_text_original": card_text[:1000],
            "features": features,
            "limits": [],
            "cta_text": cta_text,
            "cta_url": cta_url,
            "source_url": url,
            "scraped_at": scraped_at,
            "needs_review": len(card_text) > 900 or not plan_name,
        })
    deduped = {r["pricing_id"]: r for r in records}
    return list(deduped.values())


def nearest_pricing_container(text_node) -> Tag | None:
    parent = text_node.parent if hasattr(text_node, "parent") else None
    best = None
    while isinstance(parent, Tag) and parent.name not in {"body", "html"}:
        text = clean_text(parent.get_text(" ", strip=True))
        if len(text) > 1200:
            break
        classes = " ".join(parent.get("class", []))
        if parent.name in {"li", "tr"} or re.search(r"price|pricing|package|plan|card|table|elementor-widget-container", classes, re.I):
            best = parent
            if len(text) >= 30:
                break
        if not best and len(text) >= 30:
            best = parent
        parent = parent.parent
    return best


def infer_plan_name(text: str) -> str:
    parts = [part.strip(" -:") for part in re.split(r"[|\n]", text) if part.strip()]
    for part in parts[:3]:
        if len(part) <= 80 and not PRICE_RE.search(part):
            return clean_text(part)
    return ""


def billing_period(text: str) -> str:
    if re.search(r"/\s?mo|per\s+month|monthly|\bmonth\b", text, re.I):
        return "monthly"
    if re.search(r"/\s?yr|per\s+year|yearly|annually|\byear\b", text, re.I):
        return "yearly"
    if re.search(r"one[-\s]?time|fixed", text, re.I):
        return "one_time"
    return ""


def extract_pricing(soup: BeautifulSoup, url: str, service: str, scraped_at: str) -> list[dict]:
    records: list[dict] = []
    visible_soup = BeautifulSoup(str(soup.body or soup), "lxml")
    for node in visible_soup.find_all(["script", "style", "noscript", "svg", "head"]):
        node.decompose()
    records.extend(extract_elementor_price_tables(visible_soup, url, service, scraped_at))
    for card in visible_soup.select(".pricing, .price, .plan, .package, [class*=pricing], [class*=price], [class*=plan], [class*=package]"):
        classes = " ".join(card.get("class", []))
        if "elementor-price-table" in classes or card.find_parent(class_="elementor-price-table") or card.select_one(".elementor-price-table"):
            continue
        records.extend(pricing_records_from_card(card, url, service, scraped_at, len(records)))
    candidates = []
    for text_node in visible_soup.find_all(string=PRICE_RE):
        if text_node.parent and text_node.parent.name in {"script", "style", "noscript", "svg", "head"}:
            continue
        candidates.append(text_node)
    for idx, text_node in enumerate(candidates):
        text = clean_text(str(text_node))
        if any(noise in text.lower() for noise in ["language", "ajax", "nonce", "wp-admin", "elementor", "fontawesome"]):
            continue
        match = PRICE_RE.search(text)
        if not match:
            continue
        card = nearest_pricing_container(text_node)
        card_text = clean_text(card.get_text(" ", strip=True)) if card else text
        if any(noise in card_text.lower() for noise in ["language", "ajax", "nonce", "wp-admin", "elementor", "fontawesome"]):
            continue
        if not PRICING_CONTEXT_RE.search(card_text):
            continue
        plan_name = ""
        if card:
            heading = card.find(["h2", "h3", "h4", "h5", "strong"])
            plan_name = clean_text(heading.get_text(" ", strip=True)) if heading else ""
        if not plan_name:
            plan_name = infer_plan_name(card_text)
        features = []
        if card:
            features = [clean_text(li.get_text(" ", strip=True)) for li in card.find_all("li") if clean_text(li.get_text(" ", strip=True))]
        cta_text, cta_url = "", ""
        if card:
            a = card.find("a", href=True)
            if a:
                cta_text = clean_text(a.get_text(" ", strip=True))
                cta_url = normalize_url(urljoin(url, a["href"]))
        currency = match.group("currency") or match.group("currency2") or ""
        price = match.group("amount") or match.group("amount2") or None
        records.append({
            "pricing_id": stable_id("price", f"{url}|{idx}|{card_text[:100]}"),
            "service": service,
            "plan_name": plan_name,
            "price": price,
            "currency": currency,
            "billing_period": billing_period(card_text),
            "starting_from": bool(re.search(r"start|from|starting", card_text, re.I)),
            "price_text_original": card_text[:1000],
            "features": features,
            "limits": [],
            "cta_text": cta_text,
            "cta_url": cta_url,
            "source_url": url,
            "scraped_at": scraped_at,
            "needs_review": len(card_text) > 900 or not plan_name,
        })
    deduped: dict[str, dict] = {}
    for record in records:
        key = "|".join([
            record.get("source_url", ""),
            record.get("service", ""),
            record.get("plan_name", "").lower(),
            str(record.get("price", "")),
            record.get("currency", "").lower(),
            record.get("billing_period", "").lower(),
        ])
        deduped.setdefault(key, record)
    return list(deduped.values())


def extract_elementor_price_tables(soup: BeautifulSoup, url: str, service: str, scraped_at: str) -> list[dict]:
    records = []
    for idx, card in enumerate(soup.select(".elementor-price-table")):
        records.extend(pricing_records_from_card(card, url, service, scraped_at, idx))
    return records


def pricing_records_from_card(card: Tag, url: str, service: str, scraped_at: str, idx: int) -> list[dict]:
    card_text = clean_text(card.get_text(" ", strip=True))
    if not PRICING_CONTEXT_RE.search(card_text):
        return []
    match = PRICE_RE.search(card_text)
    if not match:
        return []
    plan_name = ""
    heading = card.select_one(".elementor-price-table__heading") or card.find(["h2", "h3", "h4", "h5", "strong"])
    if heading:
        plan_name = clean_text(heading.get_text(" ", strip=True))
    if not plan_name:
        plan_name = infer_plan_name(card_text)
    features = []
    feature_nodes = card.select(".elementor-price-table__features-list li, li")
    for item in feature_nodes:
        text = clean_text(item.get_text(" ", strip=True))
        if text and not PRICE_RE.search(text):
            features.append(text)
    cta_text, cta_url = "", ""
    cta = card.select_one(".elementor-price-table__button[href], a[href]")
    if cta:
        cta_text = clean_text(cta.get_text(" ", strip=True))
        cta_url = normalize_url(urljoin(url, cta["href"]))
    currency = match.group("currency") or match.group("currency2") or ""
    price = match.group("amount") or match.group("amount2") or None
    return [{
        "pricing_id": stable_id("price", f"{url}|{idx}|{card_text[:160]}"),
        "service": service,
        "plan_name": plan_name,
        "price": price,
        "currency": currency,
        "billing_period": billing_period(card_text),
        "starting_from": bool(re.search(r"start|from|starting", card_text, re.I)),
        "price_text_original": card_text[:1000],
        "features": list(dict.fromkeys(features)),
        "limits": [],
        "cta_text": cta_text,
        "cta_url": cta_url,
        "source_url": url,
        "scraped_at": scraped_at,
        "needs_review": not plan_name,
    }]


def extract_contact_info(soup: BeautifulSoup, text: str) -> list[dict]:
    contacts = []
    for email in sorted(set(EMAIL_RE.findall(text))):
        contacts.append({"type": "email", "value": email})
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("mailto:"):
            contacts.append({"type": "email", "value": unquote(href.replace("mailto:", "").split("?")[0])})
        if href.startswith("tel:"):
            contacts.append({"type": "phone", "value": unquote(href.replace("tel:", "")).strip()})
    for phone in sorted(set(PHONE_RE.findall(text))):
        digits = re.sub(r"\D", "", phone)
        if 7 <= len(digits) <= 15:
            contacts.append({"type": "phone", "value": phone})
    unique = []
    seen = set()
    for item in contacts:
        key = (item["type"], item["value"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def extract_ctas(soup: BeautifulSoup, url: str) -> list[dict]:
    ctas = []
    for a in soup.find_all("a", href=True):
        text = clean_text(a.get_text(" ", strip=True))
        if not text:
            continue
        if re.search(r"(contact|get started|quote|proposal|book|consult|call|learn more|start)", text, re.I):
            ctas.append({"text": text, "url": normalize_url(urljoin(url, a["href"]))})
    return list({f"{c['text']}|{c['url']}": c for c in ctas}.values())[:20]


def extract_forms(soup: BeautifulSoup, url: str) -> list[dict]:
    forms = []
    for idx, form in enumerate(soup.find_all("form")):
        fields = []
        for field in form.find_all(["input", "textarea", "select"]):
            name = field.get("name") or field.get("id") or ""
            field_type = field.get("type", field.name).lower()
            if field_type in FORM_FIELD_SKIP_TYPES:
                continue
            field_id = field.get("id", "")
            label = ""
            if field_id:
                label_tag = soup.find("label", attrs={"for": field_id})
                label = clean_text(label_tag.get_text(" ", strip=True)) if label_tag else ""
            fields.append({
                "name": name,
                "label": label or clean_text(field.get("placeholder", "")),
                "type": field_type,
                "selector": css_selector(field),
                "required": field.has_attr("required") or field.get("aria-required") == "true",
                "validation": field.get("pattern", ""),
            })
        if not fields:
            continue
        if len(fields) == 1 and fields[0]["type"] == "search":
            continue
        field_names = {field["name"] for field in fields}
        if field_names and field_names <= {"hide_toolbar_duration"}:
            continue
        submit = form.find(["button", "input"], attrs={"type": "submit"}) or form.find("button")
        text = clean_text(form.get_text(" ", strip=True)).lower()
        field_text = " ".join(f"{field['name']} {field['label']} {field['type']}" for field in fields).lower()
        form_haystack = f"{url} {text} {field_text}"
        form_type = (
            "newsletter" if "newsletter" in form_haystack or "subscribe" in form_haystack
            else "career" if re.search(r"career|cover letter|resume|cv|file upload", form_haystack)
            else "booking" if re.search(r"\b(book|appointment|schedule)\b", form_haystack)
            else "contact" if re.search(r"contact|message|phone|business email|business name|quote|proposal", form_haystack)
            else "other"
        )
        forms.append({
            "form_id": stable_id("form", f"{url}|{idx}"),
            "form_type": form_type,
            "page_url": url,
            "form_selector": css_selector(form),
            "fields": fields,
            "submit_selector": css_selector(submit) if submit else "",
            "captcha_detected": bool(form.select(".g-recaptcha, [class*=captcha], iframe[src*=recaptcha]")),
            "confirmation_required": True,
        })
    return forms


def css_selector(node: Tag | None) -> str:
    if not node:
        return ""
    if node.get("id"):
        return f"#{node['id']}"
    for attr in ["data-id", "data-elementor-id", "name", "aria-label"]:
        if node.get(attr):
            return f"{node.name}[{attr}='{node[attr]}']"
    classes = [c for c in node.get("class", []) if not re.search(r"\d{4,}|elementor-element-[a-f0-9]+", c)]
    if classes:
        return f"{node.name}.{'.'.join(classes[:2])}"
    return node.name


def extract_navigation_targets(soup: BeautifulSoup, url: str, page_title: str, service: str) -> list[dict]:
    nav = []
    for idx, heading in enumerate(soup.find_all(["h1", "h2", "h3"])):
        label = clean_text(heading.get_text(" ", strip=True))
        if not label:
            continue
        selector = css_selector(heading)
        nav.append({
            "navigation_id": stable_id("nav", f"{url}|{idx}|{label}"),
            "intent": label.lower(),
            "label": label,
            "service": service,
            "page_url": url,
            "page_title": page_title,
            "section_heading": label,
            "selector": selector,
            "fallback_selector": heading.name,
            "action": "navigate_and_scroll",
            "allowed_actions": ["navigate", "scroll", "highlight"],
            "requires_confirmation": False,
            "risk_level": "low",
            "validation": {
                "url_valid": True,
                "selector_found": bool(selector),
                "selector_visible": False,
                "playwright_verified": False,
            },
        })
    return nav


def extract_testimonials(soup: BeautifulSoup, url: str) -> list[dict]:
    records = []
    candidates = soup.select("blockquote, [class*=testimonial], [class*=review]")
    for idx, node in enumerate(candidates):
        text = clean_text(node.get_text(" ", strip=True))
        if len(text) < 30:
            continue
        records.append({
            "testimonial_id": stable_id("testimonial", f"{url}|{idx}|{text[:80]}"),
            "customer_name": "",
            "company": "",
            "role": "",
            "testimonial": text,
            "rating": "",
            "related_service": "",
            "source_url": url,
        })
    return records[:20]


def summarize(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", clean_text(text.replace("\n", " ")))
    return " ".join(sentences[:3])[:800]


def key_points_from_text(text: str) -> list[str]:
    lines = [clean_text(line) for line in text.splitlines()]
    return [line for line in lines if 20 <= len(line) <= 180][:12]


def extract_page(html: str, url: str, target_domain: str, scraped_at: str) -> dict:
    soup = soup_from_html(html)
    title, meta_description, language = title_and_meta(soup)
    clean = extract_clean_text(soup)
    internal, external = links(soup, url, target_domain)
    return {
        "soup": soup,
        "title": title,
        "meta_description": meta_description,
        "language": language,
        "canonical_url": canonical_url(soup, url),
        "headings": headings(soup),
        "clean_text": clean,
        "summary": summarize(clean),
        "key_points": key_points_from_text(clean),
        "internal_links": internal,
        "important_external_links": external,
        "images": images(soup, url),
        "contact_information": extract_contact_info(soup, clean),
    }
