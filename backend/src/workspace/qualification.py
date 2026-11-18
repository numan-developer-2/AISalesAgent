"""Conservative, deterministic parsing of explicitly stated qualification facts."""

import re
from decimal import Decimal


def minimum_stated_usd(value: str | None):
    text = (value or "").strip()
    if not re.search(r"\$|\bUSD\b", text, re.I):
        return None
    if re.search(
        r"\b(?:PKR|INR|CAD|AUD|SGD|NZD|HKD|under|below|less than|up to|max(?:imum)?)\b",
        text,
        re.I,
    ):
        return None
    # Only currency amounts count; project lengths and other numbers do not.
    amount = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?:\s*[kKmM]\b)?(?![\w.,])"
    currency = r"(?:\$|\bUSD\s*)"
    patterns = [
        rf"{currency}\s*(?P<first>{amount})(?:\s*(?:-|–|to)\s*(?:{currency}\s*)?(?P<second>{amount}))?",
        rf"(?<![\w.,])(?P<first>{amount})(?:\s*(?:-|–|to)\s*(?P<second>{amount}))?\s*USD\b",
    ]
    amounts = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            for value in match.groups():
                if value:
                    value = value.replace(",", "").replace(" ", "").lower()
                    unit = value[-1] if value[-1] in "km" else ""
                    amounts.append(
                        Decimal(value[:-1] if unit else value)
                        * {"": 1, "k": 1000, "m": 1000000}[unit]
                    )
    return min(amounts) if amounts else None


def has_decision_authority(value: str | None):
    text = (value or "").lower()
    if re.search(
        r"\b(?:not|no|never|without|non|unsure|unknown|don't|doesn't|cannot|can't)\b",
        text,
    ):
        return False
    return bool(
        re.search(
            r"\b(?:owner|founder|co-founder|decision[ -]maker|decision authority|authorized approver)\b",
            text,
        )
    )
