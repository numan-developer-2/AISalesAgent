from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
KNOWLEDGE_DIR = PROJECT_ROOT / "data" / "knowledge"


PRICING_TERMS = (
    "price",
    "pricing",
    "cost",
    "package",
    "plan",
    "basic",
    "standard",
    "professional",
    "monthly",
)
SERVICE_TERMS = (
    "services",
    "offer",
    "shopify",
    "seo",
    "web development",
    "website",
    "wordpress",
    "ppc",
    "google ads",
    "social media",
    "email marketing",
    "marketing",
)
COMPANY_TERMS = (
    "company",
    "who are you",
    "about",
    "contact",
    "phone",
    "email",
    "address",
)
BROAD_SERVICE_PATTERNS = (
    "what services",
    "your services",
    "services do you offer",
    "what do you do",
    "tell me about your services",
    "systematic demo studio do",
)


class StructuredKnowledgeResolver:
    def __init__(self, knowledge_dir: Path = KNOWLEDGE_DIR) -> None:
        self.knowledge_dir = knowledge_dir
        self.pricing = self._load_json("pricing.json")
        self.services = self._load_json("services.json")
        self.company_profile = self._load_json("company_profile.json")
        self.constraints = self._load_json("internal_knowledge_constraints.json")

    def _load_json(self, name: str) -> Any:
        return json.loads((self.knowledge_dir / name).read_text(encoding="utf-8"))

    def resolve(self, message: str) -> dict[str, Any]:
        lower = message.lower()
        context: dict[str, Any] = {
            "pricing": None,
            "services": None,
            "service_catalog_overview": None,
            "company_profile": None,
            "internal_policy": None,
        }
        if any(term in lower for term in PRICING_TERMS):
            context["pricing"] = self._pricing_summary()
        if any(term in lower for term in SERVICE_TERMS):
            context["services"] = self._service_summary(lower)
        if any(pattern in lower for pattern in BROAD_SERVICE_PATTERNS):
            context["service_catalog_overview"] = self._service_catalog_overview()
        if any(term in lower for term in COMPANY_TERMS):
            context["company_profile"] = self._company_summary()
        context["internal_policy"] = self._constraints_summary()
        return context

    def _pricing_summary(self) -> list[dict[str, Any]]:
        items = (
            self.pricing
            if isinstance(self.pricing, list)
            else self.pricing.get("value", [])
        )
        return [
            {
                "plan_name": item.get("plan_name"),
                "price": item.get("price"),
                "currency": item.get("currency"),
                "billing_period": item.get("billing_period"),
                "starting_from": item.get("starting_from"),
                "features": item.get("features", []),
                "source_url": item.get("source_url"),
                "exact_price_wording": self._exact_price_wording(item),
            }
            for item in items
        ]

    def _exact_price_wording(self, item: dict[str, Any]) -> str:
        plan = item.get("plan_name")
        price = item.get("price")
        currency = item.get("currency") or ""
        period = item.get("billing_period") or "month"
        if not plan or price is None or item.get("needs_review"):
            return ""
        if period == "monthly":
            period = "month"
        try:
            value = Decimal(str(price))
            if not value.is_finite() or value < 0:
                return ""
        except InvalidOperation:
            return ""
        amount = format(value, ",.2f").removesuffix(".00")
        qualifier = "starts from" if item.get("starting_from") is True else "is"
        return f"The {plan} package {qualifier} {currency}{amount} per {period}."

    def _service_catalog_overview(self) -> list[dict[str, Any]]:
        items = (
            self.services
            if isinstance(self.services, list)
            else self.services.get("value", [])
        )
        groups: dict[str, list[str]] = {}
        for item in items:
            category = item.get("category") or item.get("parent_service") or "Other"
            service_name = item.get("service_name")
            if not service_name:
                continue
            groups.setdefault(category, [])
            if service_name not in groups[category]:
                groups[category].append(service_name)
        return [
            {"category": category, "services": services[:8]}
            for category, services in sorted(groups.items())
        ][:8]

    def _service_summary(self, lower_message: str) -> list[dict[str, Any]]:
        items = (
            self.services
            if isinstance(self.services, list)
            else self.services.get("value", [])
        )
        selected = []
        for item in items:
            searchable = " ".join(
                [
                    str(item.get("service_name", "")),
                    str(item.get("category", "")),
                    str(item.get("parent_service", "")),
                    " ".join(item.get("aliases", []) or []),
                ]
            ).lower()
            if any(
                term in lower_message and term in searchable for term in SERVICE_TERMS
            ):
                selected.append(item)
        if not selected:
            selected = items[:8]
        return [
            {
                "service_name": item.get("service_name"),
                "category": item.get("category"),
                "parent_service": item.get("parent_service"),
                "description": item.get("description"),
                "primary_url": item.get("primary_url"),
                "source_confidence": item.get("source_confidence"),
                "limitations": item.get("limitations"),
            }
            for item in selected[:8]
        ]

    def _company_summary(self) -> dict[str, Any]:
        return {
            "company_name": self.company_profile.get("company_name"),
            "website": self.company_profile.get("website"),
            "description": self.company_profile.get("description"),
            "emails": self.company_profile.get("emails", []),
            "phone_numbers": self.company_profile.get("phone_numbers", []),
            "contact_urls": self.company_profile.get("contact_urls", []),
            "services": self.company_profile.get("services", [])[:20],
        }

    def _constraints_summary(self) -> dict[str, Any]:
        constraints = (
            self.constraints.get("service_constraints", [])
            if isinstance(self.constraints, dict)
            else []
        )
        return {
            "purpose": "Internal policy context only. Do not quote directly to users.",
            "service_limitations": [
                {
                    "service_name": item.get("canonical_service_name")
                    or item.get("service_name"),
                    "answer_scope": item.get("answer_scope"),
                    "limitations": item.get("limitations"),
                }
                for item in constraints[:8]
            ],
        }
