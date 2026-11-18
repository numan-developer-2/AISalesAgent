from __future__ import annotations

from abc import ABC, abstractmethod

from .models import LLMRequest, LLMResponse


class LLMProviderError(RuntimeError):
    pass


class LLMQuotaExceededError(LLMProviderError):
    def __init__(self, provider: str, retry_after_seconds: int | None = None) -> None:
        self.provider = provider
        self.reason = "quota_exceeded"
        self.retry_after_seconds = retry_after_seconds
        message = f"{provider} quota exceeded"
        if retry_after_seconds is not None:
            message = f"{message}; retry_after_seconds={retry_after_seconds}"
        super().__init__(message)


class LLMTransientUnavailableError(LLMProviderError):
    def __init__(self, provider: str, retry_after_seconds: int | None = None) -> None:
        self.provider = provider
        self.reason = "transient_unavailable"
        self.retry_after_seconds = retry_after_seconds
        message = f"{provider} temporarily unavailable"
        if retry_after_seconds is not None:
            message = f"{message}; retry_after_seconds={retry_after_seconds}"
        super().__init__(message)


class LLMProvider(ABC):
    @abstractmethod
    def generate_structured(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError
