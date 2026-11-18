from __future__ import annotations

import hashlib
import re


def normalized_text_for_hash(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def sha256_text(text: str) -> str:
    return hashlib.sha256(normalized_text_for_hash(text).encode("utf-8")).hexdigest()


def stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"
