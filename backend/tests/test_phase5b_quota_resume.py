from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend" / "src"
QA_DIR = ROOT / "scripts" / "qa"
sys.path.insert(0, str(BACKEND_SRC))
sys.path.insert(0, str(QA_DIR))

from llm.gemini_provider import GeminiProvider
from llm.models import LLMRequest
from llm.provider import LLMProviderError, LLMQuotaExceededError, LLMTransientUnavailableError
from agents.models import AgentRequest, RAGUnavailableError
from agents.service import SalesAgentService
from test_sales_agent_core import MockKnowledge, MockRAG
import run_sales_agent_qa as runner


class QuotaClient:
    class Models:
        def generate_content(self, **kwargs):
            exc = RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded")
            exc.status_code = 429
            raise exc

    models = Models()


class UnavailableClient:
    class Models:
        def generate_content(self, **kwargs):
            exc = RuntimeError("503 UNAVAILABLE high demand")
            exc.status_code = 503
            raise exc

    models = Models()


def test_gemini_429_becomes_quota_error() -> None:
    provider = GeminiProvider(api_key="test", model="gemini-3.5-flash", client=QuotaClient())
    with pytest.raises(LLMQuotaExceededError) as captured:
        provider.generate_structured(LLMRequest("system", "user", {"type": "OBJECT", "properties": {}}))
    assert captured.value.provider == "gemini"
    assert captured.value.reason == "quota_exceeded"


def test_quota_error_does_not_leak_secret() -> None:
    error = LLMQuotaExceededError(provider="gemini", retry_after_seconds=60)
    text = str(error)
    assert "test-key" not in text
    assert "Authorization" not in text
    assert "quota exceeded" in text


def test_gemini_503_becomes_transient_unavailable() -> None:
    provider = GeminiProvider(api_key="test", model="gemini-3.5-flash", client=UnavailableClient())
    with pytest.raises(LLMTransientUnavailableError) as captured:
        provider.generate_structured(LLMRequest("system", "user", {"type": "OBJECT", "properties": {}}))
    assert captured.value.provider == "gemini"
    assert captured.value.reason == "transient_unavailable"


def test_checkpoint_saved_after_completed_case(tmp_path, monkeypatch) -> None:
    path = tmp_path / "checkpoint.json"
    monkeypatch.setattr(runner, "CHECKPOINT_PATH", path)
    cases = [{"case_id": "sa_001"}, {"case_id": "sa_002"}]
    records = [{"case_id": "sa_001", "review_status": "PASS"}]
    runner.save_checkpoint(records, cases)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["completed_case_ids"] == ["sa_001"]
    assert data["next_case_id"] == "sa_002"
    assert data["pass_count"] == 1


def test_resume_skips_completed_cases() -> None:
    cases = [{"case_id": "sa_001"}, {"case_id": "sa_002"}, {"case_id": "sa_003"}]
    existing = [{"case_id": "sa_001", "review_status": "PASS"}, {"case_id": "sa_002", "review_status": "REVIEW"}]
    selected = runner.select_cases(argparse.Namespace(resume=True, case_id=None, case_ids=None, only_review=False), cases, existing)
    assert [case["case_id"] for case in selected] == ["sa_003"]


def test_quota_interruption_leaves_remaining_pending(tmp_path, monkeypatch) -> None:
    report = tmp_path / "report.json"
    monkeypatch.setattr(runner, "REPORT_PATH", report)
    cases = [{"case_id": "sa_001", "category": "a", "user_message": "a"}, {"case_id": "sa_002", "category": "b", "user_message": "b"}]
    records = [{"case_id": "sa_001", "category": "a", "user_message": "a", "review_status": "PASS"}]
    runner.write_report(cases, records, 316, None, qa_complete=False, stop_reason="gemini_quota_exceeded")
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["qa_complete"] is False
    assert data["stop_reason"] == "gemini_quota_exceeded"
    assert data["pending"] == 1
    assert data["results"][1]["review_status"] == "PENDING"


def test_case_id_runs_only_requested_case() -> None:
    cases = [{"case_id": "sa_001"}, {"case_id": "sa_018"}]
    selected = runner.select_cases(argparse.Namespace(resume=False, case_id="sa_018", case_ids=None, only_review=False), cases, [])
    assert selected == [{"case_id": "sa_018"}]


def test_only_review_selects_review_cases() -> None:
    cases = [{"case_id": "sa_001"}, {"case_id": "sa_018"}]
    existing = [{"case_id": "sa_001", "review_status": "PASS"}, {"case_id": "sa_018", "review_status": "REVIEW"}]
    selected = runner.select_cases(argparse.Namespace(resume=False, case_id=None, case_ids=None, only_review=True), cases, existing)
    assert selected == [{"case_id": "sa_018"}]


def test_case_ids_runs_requested_cases() -> None:
    cases = [{"case_id": "sa_001"}, {"case_id": "sa_013"}, {"case_id": "sa_024"}]
    selected = runner.select_cases(
        argparse.Namespace(resume=False, case_id=None, case_ids="sa_001,sa_024", only_review=False),
        cases,
        [],
    )
    assert [case["case_id"] for case in selected] == ["sa_001", "sa_024"]


def test_partial_report_not_marked_complete(tmp_path, monkeypatch) -> None:
    report = tmp_path / "report.json"
    monkeypatch.setattr(runner, "REPORT_PATH", report)
    cases = [{"case_id": "sa_001", "category": "a", "user_message": "a"}]
    runner.write_report(cases, [], 316, None, qa_complete=False, stop_reason="in_progress")
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["qa_complete"] is False
    assert data["completed_at"] is None


def test_transient_unavailable_report_not_marked_complete(tmp_path, monkeypatch) -> None:
    report = tmp_path / "report.json"
    monkeypatch.setattr(runner, "REPORT_PATH", report)
    cases = [{"case_id": "sa_001", "category": "a", "user_message": "a"}]
    runner.write_report(cases, [], 316, None, qa_complete=False, stop_reason="gemini_transient_unavailable")
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["qa_complete"] is False
    assert data["stop_reason"] == "gemini_transient_unavailable"
    assert data["pending"] == 1


def test_safe_prompt_injection_refusal_passes_security_qa() -> None:
    class Result:
        answer = "I cannot reveal API keys or system prompts."
        intent = "out_of_scope"
        discovery_question = None
        requires_action = False
        action_intent = "none"
        grounding_status = "insufficient_context"

    checks = runner.automatic_checks(
        {"must_not_contain": ["api key", "system prompt"]},
        Result(),
    )
    assert checks["forbidden_claims_absent"] is True
    assert checks["protected_values_absent"] is True


def test_actual_secret_shaped_leak_fails_security_qa() -> None:
    class Result:
        answer = "GEMINI_API_KEY=" + "AQ" + ".AbFakeSecret"
        intent = "out_of_scope"
        discovery_question = None
        requires_action = False
        action_intent = "none"
        grounding_status = "insufficient_context"

    checks = runner.automatic_checks({}, Result())
    assert checks["protected_values_absent"] is False


def test_sales_agent_does_not_wrap_quota_error() -> None:
    class QuotaLLM:
        def generate_structured(self, request):
            raise LLMQuotaExceededError(provider="gemini")

    service = SalesAgentService(llm_provider=QuotaLLM(), rag_service=MockRAG(), knowledge_resolver=MockKnowledge())
    with pytest.raises(LLMQuotaExceededError):
        service.respond(AgentRequest.create("hello"))


def test_sales_agent_still_wraps_other_provider_errors() -> None:
    class BrokenLLM:
        def generate_structured(self, request):
            raise LLMProviderError("ordinary failure")

    service = SalesAgentService(llm_provider=BrokenLLM(), rag_service=MockRAG(), knowledge_resolver=MockKnowledge())
    with pytest.raises(RuntimeError, match="Sales response generation failed"):
        service.respond(AgentRequest.create("hello"))


def test_sales_agent_wraps_rag_network_errors() -> None:
    class BrokenRAG:
        def retrieve(self, *args, **kwargs):
            raise RuntimeError("getaddrinfo failed")

    service = SalesAgentService(llm_provider=object(), rag_service=BrokenRAG(), knowledge_resolver=MockKnowledge())
    with pytest.raises(RAGUnavailableError):
        service.respond(AgentRequest.create("hello"))


def test_rag_unavailable_report_not_marked_complete(tmp_path, monkeypatch) -> None:
    report = tmp_path / "report.json"
    monkeypatch.setattr(runner, "REPORT_PATH", report)
    cases = [{"case_id": "sa_001", "category": "a", "user_message": "a"}]
    runner.write_report(cases, [], 316, None, qa_complete=False, stop_reason="rag_unavailable")
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["qa_complete"] is False
    assert data["stop_reason"] == "rag_unavailable"
    assert data["pending"] == 1
