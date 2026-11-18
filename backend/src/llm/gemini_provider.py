from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

from .models import LLMRequest, LLMResponse
from .provider import (
    LLMProvider,
    LLMProviderError,
    LLMQuotaExceededError,
    LLMTransientUnavailableError,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_CHAT_MODEL = "gemini-3.5-flash"


class GeminiProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        client: Any | None = None,
    ) -> None:
        if api_key is None or model is None:
            load_dotenv(ENV_PATH)
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
        self.model = model or os.getenv("GEMINI_CHAT_MODEL", DEFAULT_CHAT_MODEL).strip()
        if not self.api_key:
            raise LLMProviderError("GEMINI_API_KEY is missing")
        if not self.model:
            raise LLMProviderError("GEMINI_CHAT_MODEL is missing")
        self.client = client or genai.Client(
            api_key=self.api_key,
            http_options=types.HttpOptions(
                timeout=45000, retry_options=types.HttpRetryOptions(attempts=1)
            ),
        )

    def generate_structured(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self.model
        try:
            response = self.client.models.generate_content(
                model=model,
                contents=request.user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=request.system_prompt,
                    response_mime_type="application/json",
                    response_schema=request.response_schema,
                ),
            )
        except Exception as exc:
            if self._is_quota_exceeded(exc):
                raise LLMQuotaExceededError(
                    provider="gemini",
                    retry_after_seconds=self._retry_after_seconds(exc),
                ) from exc
            if self._is_transient_unavailable(exc):
                raise LLMTransientUnavailableError(
                    provider="gemini",
                    retry_after_seconds=self._retry_after_seconds(exc),
                ) from exc
            raise LLMProviderError("Gemini response generation failed") from exc

        text = getattr(response, "text", None)
        if not text:
            raise LLMProviderError("Gemini returned an empty response")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMProviderError("Gemini structured output was invalid JSON") from exc
        if not isinstance(data, dict):
            raise LLMProviderError("Gemini structured output must be an object")
        return LLMResponse(data=data, model=model, raw_text=text)

    def _is_quota_exceeded(self, exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        if status_code == 429:
            return True
        text = str(exc).upper()
        return "RESOURCE_EXHAUSTED" in text or "429" in text

    def _retry_after_seconds(self, exc: Exception) -> int | None:
        retry_after = getattr(exc, "retry_after", None)
        if isinstance(retry_after, int):
            return retry_after
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", {}) if response is not None else {}
        value = (
            headers.get("retry-after") or headers.get("Retry-After")
            if headers
            else None
        )
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _is_transient_unavailable(self, exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        if status_code in (500, 502, 503, 504):
            return True
        text = str(exc).upper()
        return "UNAVAILABLE" in text or "HIGH DEMAND" in text or "503" in text
