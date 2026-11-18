"""Optional bounded live-model acceptance probe using public business knowledge only."""

import argparse
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))
from workspace.config import Settings, secret, validate_business
from workspace.database import Database
from workspace.engine import initialize, respond


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Explicitly call the configured Gemini account (up to three requests)",
    )
    args = parser.parse_args()
    output = ROOT / "artifacts" / "backend-answer-qa" / uuid4().hex
    output.mkdir(parents=True, exist_ok=True)
    settings = Settings(mode="demo")
    if not args.live:
        print(
            "Use --live only when ready to test the configured provider. Offline regressions are in backend/tests/test_workspace_answer_quality.py."
        )
        return 0
    if not secret(settings, "systematic", "GEMINI_API_KEY"):
        print("Live acceptance unavailable: no configured Gemini key.")
        return 2
    db = Database(
        "sqlite:///" + (output / ("answer-probe-" + uuid4().hex + ".db")).as_posix()
    )
    business = validate_business(
        json.loads(
            (ROOT / "config/businesses/systematic.json").read_text(encoding="utf-8")
        )
    )
    initialize(db, settings, [business])
    # Local retrieval only; this probe cannot contact CRM, Calendar, SMTP or Supabase.
    live = SimpleNamespace(mode="live", env={**settings.env, "RAG_PROVIDER": "local"})
    cases = [
        "How can your SEO services help a small local business?",
        "Are you ISO 27001 certified?",
        "Mujhe Google number one ranking ki guarantee chahiye, kya guarantee hai?",
    ]
    rows = []
    for message in cases:
        started = time.monotonic()
        try:
            result = respond(
                db, live, db.get("systematic", "business", "systematic"), message, []
            )
            rows.append(
                {
                    "question": message,
                    "answer": result["answer"],
                    "grounding_status": result.get("grounding_status"),
                    "sources": result["sources"],
                    "status": "response_received; human relevance review required",
                    "duration_seconds": round(time.monotonic() - started, 2),
                }
            )
            print(
                json.dumps(
                    {
                        "case": len(rows),
                        "status": "response_received",
                        "grounding_status": result.get("grounding_status"),
                    }
                ),
                flush=True,
            )
        except Exception as exc:
            rows.append(
                {
                    "question": message,
                    "status": "provider_or_output_failure",
                    "error_type": type(exc).__name__,
                    "duration_seconds": round(time.monotonic() - started, 2),
                }
            )
            print(
                "Live probe stopped: "
                + type(exc).__name__
                + ". No credential or provider error body was printed.",
                flush=True,
            )
            break
    (output / "live-answer-probe.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    db.engine.dispose()
    print(json.dumps({"report": str(output / "live-answer-probe.json")}), flush=True)
    return 0 if len(rows) == len(cases) and all("answer" in r for r in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
