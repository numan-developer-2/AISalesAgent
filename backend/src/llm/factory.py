from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from .gemini_provider import GeminiProvider
from .provider import LLMProvider, LLMProviderError


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = PROJECT_ROOT / ".env"


def create_llm_provider(provider_name: str | None = None) -> LLMProvider:
    load_dotenv(ENV_PATH)
    provider = (provider_name or os.getenv("LLM_PROVIDER", "gemini")).strip().lower()
    if provider == "gemini":
        return GeminiProvider()
    raise LLMProviderError(f"Unsupported LLM provider: {provider}")
