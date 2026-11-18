from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import create_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = PROJECT_ROOT / "backend" / "src"
CASES_PATH = PROJECT_ROOT / "data" / "examples" / "sales_agent_qa_cases.json"
REPORT_PATH = PROJECT_ROOT / "data" / "reports" / "sales_agent_qa_report.json"
CHECKPOINT_PATH = PROJECT_ROOT / "data" / "reports" / "sales_agent_qa_checkpoint.json"
EXPECTED_ROWS = 5  # Fictional bundled corpus; adapt when replacing it.
QUOTA_EXIT_CODE = 75

sys.path.insert(0, str(BACKEND_SRC))

from agents.models import AgentRequest, RAGUnavailableError  # noqa: E402
from agents.service import SalesAgentService  # noqa: E402
from llm.provider import LLMQuotaExceededError, LLMTransientUnavailableError  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run resume-safe live Sales Agent QA.")
    parser.add_argument("--resume", action="store_true", help="Skip completed case IDs from prior report.")
    parser.add_argument("--case-id", help="Run exactly one QA case ID.")
    parser.add_argument("--case-ids", help="Run a comma-separated list of QA case IDs.")
    parser.add_argument("--only-review", action="store_true", help="Run only cases currently marked REVIEW.")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_cases() -> list[dict[str, Any]]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def load_existing_results() -> list[dict[str, Any]]:
    if not REPORT_PATH.exists():
        return []
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    results = report.get("results", [])
    return results if isinstance(results, list) else []


def save_checkpoint(records: list[dict[str, Any]], cases: list[dict[str, Any]]) -> None:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    completed = [record["case_id"] for record in records if record.get("review_status") in ("PASS", "REVIEW", "FAIL")]
    remaining = [case["case_id"] for case in cases if case["case_id"] not in set(completed)]
    checkpoint = {
        "completed_case_ids": completed,
        "next_case_id": remaining[0] if remaining else None,
        "pass_count": sum(1 for item in records if item.get("review_status") == "PASS"),
        "review_count": sum(1 for item in records if item.get("review_status") == "REVIEW"),
        "failed_count": sum(1 for item in records if item.get("review_status") == "FAIL"),
        "updated_at": utc_now(),
    }
    CHECKPOINT_PATH.write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")


def row_count() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    url = os.getenv("SUPABASE_URL", "").strip()
    secret = os.getenv("SUPABASE_SECRET_KEY", "").strip()
    if not url or not secret:
        raise RuntimeError("SUPABASE_URL or SUPABASE_SECRET_KEY is missing")
    client = create_client(url, secret)
    response = client.table("knowledge_chunks").select("id", count="exact").limit(1).execute()
    return int(response.count or 0)


def contains_any(text: str, terms: list[str]) -> bool:
    lower = text.lower()
    return any(term.lower() in lower for term in terms)


def leaks_protected_value(text: str) -> bool:
    lower = text.lower()
    secret_markers = [
        "gemini_api_key=",
        "supabase_secret_key=",
        "sb_" + "secret_",
        "sb_" + "publishable_",
        "aq" + ".ab",
        "-----begin",
    ]
    return any(marker in lower for marker in secret_markers)


def automatic_checks(case: dict[str, Any], result: Any) -> dict[str, bool]:
    answer = result.answer or ""
    checks: dict[str, bool] = {}
    expected_intents = case.get("expected_intents")
    if expected_intents:
        checks["intent"] = result.intent in expected_intents
    expected_terms = case.get("expected_terms")
    if expected_terms:
        checks["expected_terms"] = contains_any(answer, expected_terms)
    if case.get("expected_discovery_question"):
        checks["discovery_question"] = bool(result.discovery_question)
    if "expected_requires_action" in case:
        checks["requires_action"] = result.requires_action is bool(case["expected_requires_action"])
    if case.get("expected_action_intent"):
        checks["action_intent"] = result.action_intent == case["expected_action_intent"]
    if case.get("expected_grounding"):
        checks["grounding_status"] = result.grounding_status in case["expected_grounding"]
    must_not = case.get("must_not_contain") or []
    if must_not:
        filtered = [
            term
            for term in must_not
            if term.lower() not in ("api key", "api keys", "system prompt", "hidden system prompt")
        ]
        checks["forbidden_claims_absent"] = not contains_any(answer, filtered) if filtered else True
    checks["protected_values_absent"] = not leaks_protected_value(answer)
    return checks


def pending_record(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "user_message": case["user_message"],
        "intent": None,
        "grounding_status": None,
        "recommended_services": [],
        "requires_action": None,
        "action_intent": None,
        "sources_count": 0,
        "grounding_sources": [],
        "answer": None,
        "automatic_checks": {},
        "review_status": "PENDING",
    }


def run_case(service: SalesAgentService, case: dict[str, Any]) -> dict[str, Any]:
    result = service.respond(AgentRequest.create(case["user_message"]))
    checks = automatic_checks(case, result)
    review_status = "PASS" if all(checks.values()) else "REVIEW"
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "user_message": case["user_message"],
        "intent": result.intent,
        "grounding_status": result.grounding_status,
        "recommended_services": result.recommended_services,
        "requires_action": result.requires_action,
        "action_intent": result.action_intent,
        "sources_count": len(result.sources),
        "grounding_sources": result.grounding_sources,
        "answer": result.answer,
        "automatic_checks": checks,
        "review_status": review_status,
    }


def select_cases(args: argparse.Namespace, cases: list[dict[str, Any]], existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if args.case_ids:
        requested = [case_id.strip() for case_id in args.case_ids.split(",") if case_id.strip()]
        selected = [case for case in cases if case["case_id"] in requested]
        found = {case["case_id"] for case in selected}
        missing = [case_id for case_id in requested if case_id not in found]
        if missing:
            raise RuntimeError(f"Unknown case_id(s): {', '.join(missing)}")
        return selected
    if args.case_id:
        selected = [case for case in cases if case["case_id"] == args.case_id]
        if not selected:
            raise RuntimeError(f"Unknown case_id: {args.case_id}")
        return selected
    if args.only_review:
        review_ids = {item["case_id"] for item in existing if item.get("review_status") == "REVIEW"}
        return [case for case in cases if case["case_id"] in review_ids]
    if args.resume:
        completed = {item["case_id"] for item in existing if item.get("review_status") in ("PASS", "REVIEW", "FAIL")}
        return [case for case in cases if case["case_id"] not in completed]
    return cases


def merge_record(records: list[dict[str, Any]], record: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in records if item.get("case_id") != record["case_id"]] + [record]


def ordered_records(cases: list[dict[str, Any]], records: list[dict[str, Any]], include_pending: bool) -> list[dict[str, Any]]:
    by_id = {item["case_id"]: item for item in records}
    output = []
    for case in cases:
        if case["case_id"] in by_id:
            output.append(by_id[case["case_id"]])
        elif include_pending:
            output.append(pending_record(case))
    return output


def write_report(
    cases: list[dict[str, Any]],
    records: list[dict[str, Any]],
    rows_before: int,
    rows_after: int | None,
    qa_complete: bool,
    stop_reason: str | None,
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    final_records = ordered_records(cases, records, include_pending=not qa_complete)
    report = {
        "model": os.getenv("GEMINI_CHAT_MODEL", "gemini-3.5-flash"),
        "database_rows_before": rows_before,
        "database_rows_after": rows_after,
        "database_writes": 0,
        "qa_complete": qa_complete,
        "stop_reason": stop_reason,
        "total_cases": len(final_records),
        "passed": sum(1 for item in final_records if item["review_status"] == "PASS"),
        "review": sum(1 for item in final_records if item["review_status"] == "REVIEW"),
        "failed": sum(1 for item in final_records if item["review_status"] == "FAIL"),
        "pending": sum(1 for item in final_records if item["review_status"] == "PENDING"),
        "results": final_records,
        "completed_at": utc_now() if qa_complete else None,
        "updated_at": utc_now(),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    cases = load_cases()
    existing = load_existing_results()
    selected = select_cases(args, cases, existing)
    rows_before = row_count()
    if rows_before != EXPECTED_ROWS:
        raise RuntimeError(f"Expected {EXPECTED_ROWS} knowledge rows before QA, found {rows_before}")
    records = existing[:]
    service = SalesAgentService()
    try:
        for case in selected:
            record = run_case(service, case)
            records = merge_record(records, record)
            save_checkpoint(records, cases)
            write_report(cases, records, rows_before, None, qa_complete=False, stop_reason="in_progress")
            print(f"{case['case_id']} {record['review_status']} {case['category']} -> {record['intent']}")
    except LLMQuotaExceededError:
        completed = [item for item in records if item.get("review_status") in ("PASS", "REVIEW", "FAIL")]
        remaining = [case for case in cases if case["case_id"] not in {item["case_id"] for item in completed}]
        save_checkpoint(records, cases)
        write_report(cases, records, rows_before, None, qa_complete=False, stop_reason="gemini_quota_exceeded")
        print("QA PAUSED - GEMINI QUOTA EXHAUSTED")
        print(f"completed_cases: {len(completed)}")
        print(f"next_case: {remaining[0]['case_id'] if remaining else 'none'}")
        print("progress_saved: YES")
        return QUOTA_EXIT_CODE
    except LLMTransientUnavailableError:
        completed = [item for item in records if item.get("review_status") in ("PASS", "REVIEW", "FAIL")]
        remaining = [case for case in cases if case["case_id"] not in {item["case_id"] for item in completed}]
        save_checkpoint(records, cases)
        write_report(cases, records, rows_before, None, qa_complete=False, stop_reason="gemini_transient_unavailable")
        print("QA PAUSED - GEMINI TEMPORARILY UNAVAILABLE")
        print(f"completed_cases: {len(completed)}")
        print(f"next_case: {remaining[0]['case_id'] if remaining else 'none'}")
        print("progress_saved: YES")
        return QUOTA_EXIT_CODE
    except RAGUnavailableError:
        completed = [item for item in records if item.get("review_status") in ("PASS", "REVIEW", "FAIL")]
        remaining = [case for case in cases if case["case_id"] not in {item["case_id"] for item in completed}]
        save_checkpoint(records, cases)
        write_report(cases, records, rows_before, None, qa_complete=False, stop_reason="rag_unavailable")
        print("QA PAUSED - RAG/SUPABASE TEMPORARILY UNAVAILABLE")
        print(f"completed_cases: {len(completed)}")
        print(f"next_case: {remaining[0]['case_id'] if remaining else 'none'}")
        print("progress_saved: YES")
        return QUOTA_EXIT_CODE

    rows_after = row_count()
    if rows_after != EXPECTED_ROWS:
        raise RuntimeError(f"Expected {EXPECTED_ROWS} knowledge rows after QA, found {rows_after}")
    all_records = ordered_records(cases, records, include_pending=True)
    qa_complete = all(item["review_status"] != "PENDING" for item in all_records)
    write_report(cases, records, rows_before, rows_after, qa_complete=qa_complete, stop_reason=None if qa_complete else "pending_cases")
    save_checkpoint(records, cases)
    print(f"report_written: {REPORT_PATH}")
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
