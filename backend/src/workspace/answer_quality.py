"""Conservative checks on model output; these are not semantic truth certification."""

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import json
import re

from agents.models import SALES_RESPONSE_SCHEMA
from workspace.qualification import has_decision_authority

GROUNDED_SCHEMA = deepcopy(SALES_RESPONSE_SCHEMA)
GROUNDED_SCHEMA["properties"]["evidence"] = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {"source_id": {"type": "STRING"}, "quote": {"type": "STRING"}},
        "required": ["source_id", "quote"],
    },
}
GROUNDED_SCHEMA["required"].append("evidence")


def normalized(text):
    return " ".join(text.casefold().split())


def suspicious_reference(text):
    return bool(
        re.search(
            r"ignore (?:all |previous |the )*(?:instructions|rules)|system prompt|developer message|reveal.*(?:secret|api.key)|<\|(?:system|im_start)\|>",
            text,
            re.I,
        )
    )


def fallback(message):
    roman = re.search(
        r"\b(kia|kya|hai|hain|mujhe|muje|batao|kitna|kitni|chahiye|aap)\b",
        message,
        re.I,
    )
    urdu = re.search(r"[\u0600-\u06ff]", message)
    answer = (
        "Mere paas is baat ko confirm karne ke liye kafi approved information nahi hai. Aap sales team se confirmation le sakte hain."
        if roman
        else (
            "میرے پاس اس بات کی تصدیق کے لیے کافی منظور شدہ معلومات نہیں ہیں۔ آپ سیلز ٹیم سے تصدیق کر سکتے ہیں۔"
            if urdu
            else "I don't have enough approved information to confirm that. You can ask the sales team to verify the details."
        )
    )
    return {
        "answer": answer,
        "intent": "general_information",
        "action": "human_handover",
        "services": [],
        "lead_updates": {},
        "sources": [],
        "grounding_status": "insufficient_context",
    }


def grounded_evidence(data, records):
    evidence = data.get("evidence")
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 5:
        return []
    indexed = {r["id"]: r for r in records}
    validated = []
    for item in evidence:
        if not isinstance(item, dict):
            return []
        if not isinstance(item.get("source_id"), str):
            return []
        source, quote = indexed.get(item.get("source_id")), item.get("quote")
        if not source or not isinstance(quote, str) or not 12 <= len(quote) <= 1200:
            return []
        if normalized(quote) not in normalized(source["content"]):
            return []
        validated.append({**source, "quote": quote})
    return validated


def unsafe_answer(answer, evidence):
    # URLs/contact addresses and numerical claims must appear in cited excerpts.
    approved = normalized("\n".join(e["quote"] for e in evidence))
    claims = re.findall(
        r"https?://[^\s)]+|[\w.+-]+@[\w.-]+\.[a-z]{2,}|(?<!\w)[$£€]?\d[\d,.]*(?:\s*%|[kKmM]\b)?",
        answer,
        re.I,
    )
    if any(
        not re.search(
            r"(?<![\w.,])" + re.escape(normalized(claim).rstrip(".,")) + r"(?![\w.,])",
            approved,
        )
        for claim in claims
    ):
        return True
    # The chat model has no authority to report completed external actions.
    if re.search(
        r"\b(?:booked|scheduled|sent|submitted|charged|refunded|guarantee[ds]?|certified|accredited|discount)\b",
        answer,
        re.I,
    ):
        return True
    return suspicious_reference(answer)


def render_evidence(evidence, business, message):
    """Use checked excerpts instead of publishing unchecked generated factual prose."""
    if all(row["id"] == "business-catalog" for row in evidence):
        return (
            f"{business['name']} lists these services: "
            + ", ".join(business["services"])
            + "."
        )
    quotes = list(
        dict.fromkeys(
            row["quote"].strip() for row in evidence if row["id"] != "business-catalog"
        )
    )
    if re.search(r"\b(kia|kya|hai|hain|mujhe|muje|batao|aap)\b", message, re.I):
        intro = "Approved business information mein yeh likha hai (original text):"
    elif re.search(r"[\u0600-\u06ff]", message):
        intro = "منظور شدہ کاروباری معلومات میں یہ درج ہے (اصل متن):"
    else:
        intro = "The approved business information says:"
    return intro + "\n\n" + "\n\n".join(quotes[:3])


def explicit_updates(updates, message, services):
    # A hallucinated model field must not become a stored qualification fact.
    accepted = {}
    for key, value in updates.items():
        if key == "authority_status" and not has_decision_authority(message):
            continue
        if key == "budget_range" and re.search(
            r"\b(?:up to|under|below|max(?:imum)?|less than)\b", message, re.I
        ):
            # Preserve the ceiling rather than turning it into a stated minimum.
            accepted[key] = message
            continue
        if key == "required_services" and isinstance(value, list):
            accepted[key] = [
                s
                for s in value
                if isinstance(s, str)
                and s in services
                and normalized(s) in normalized(message)
            ]
        elif (
            isinstance(value, str)
            and value.strip()
            and normalized(value) in normalized(message)
        ):
            accepted[key] = value
    return accepted


def format_prices(plans, message, services):
    """Only exact reviewed prices. Unmapped plans cannot be quoted for another service."""
    matches = [s for s in services if normalized(s) in normalized(message)]
    lines = []
    for plan in plans:
        if plan.get("needs_review") is not False:
            continue
        service = plan.get("service") or ""
        if not service and (
            matches
            or re.search(
                r"\b(?:website|wordpress|shopify|seo|ads|design|marketing|development)\b",
                message,
                re.I,
            )
        ):
            continue
        if matches and not any(
            normalized(s) in normalized(service) or normalized(service) in normalized(s)
            for s in matches
        ):
            continue
        try:
            price = Decimal(str(plan["price"]))
            if not price.is_finite() or price < 0:
                continue
        except (KeyError, InvalidOperation):
            continue
        currency = plan.get("currency")
        if currency not in ("$", "USD", "£", "GBP", "€", "EUR", "PKR"):
            continue
        amount = format(price, ",.2f").removesuffix(".00")
        period = {
            "monthly": "per month",
            "yearly": "per year",
            "one_time": "one time",
        }.get(plan.get("billing_period"))
        if not period or not plan.get("plan_name"):
            continue
        qualifier = "from " if plan.get("starting_from") is True else ""
        lines.append(
            f"{service or 'Published plan (service not specified)'} — {plan['plan_name']}: {qualifier}{currency} {amount} {period}."
        )
    return "\n".join(lines)


def catalog_record(business):
    return {
        "id": "business-catalog",
        "title": "Business service catalog",
        "source_url": business["website"],
        "content": json.dumps(
            {
                "name": business["name"],
                "services": business["services"],
                "website": business["website"],
            },
            ensure_ascii=False,
        ),
    }
