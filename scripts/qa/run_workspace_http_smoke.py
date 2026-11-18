"""Run an isolated demo API and worker, exercise HTTP workflows, then stop both."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend/app" if (ROOT / "frontend/app/package.json").is_file() else ROOT


def stop(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def main():
    folder = ROOT / "artifacts" / "backend-http-qa" / ("http-" + uuid4().hex)
    folder.mkdir(parents=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "backend/src"),
        "APP_MODE": "demo",
        "APP_ORIGIN": origin,
        "COOKIE_SECURE": "false",
        "APP_DATABASE_URL": "sqlite:///" + (folder / "demo.db").as_posix(),
        "BUSINESS_CONFIG_DIR": str(ROOT / "config/businesses"),
    }
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    api_process = worker = None
    checks = []
    with (folder / "server.log").open("w", encoding="utf-8") as log:

        def start():
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "workspace.api:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=log,
                creationflags=flags,
            )
            try:
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("Demo server exited during startup")
                    try:
                        if (
                            httpx.get(origin + "/api/health", timeout=1).status_code
                            == 200
                        ):
                            return process
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.2)
                raise RuntimeError("Demo server startup timed out")
            except Exception:
                stop(process)
                raise

        try:
            api_process = start()
            with httpx.Client(
                base_url=origin,
                headers={"Origin": origin, "X-Workspace-Request": "1"},
                timeout=10,
            ) as client:
                for path in ("/", "/demo", "/widget", "/embed.js", "/api/health"):
                    assert client.get(path).status_code == 200, path
                checks.append("built application routes")
                asset = next((FRONTEND / "dist/assets").glob("*.js"))
                partial = client.get(
                    "/assets/" + asset.name, headers={"Range": "bytes=0-31"}
                )
                assert partial.status_code == 206 and len(partial.content) == 32
                assert client.get("/api/admin/workspace").status_code == 401
                assert (
                    client.post(
                        "/api/auth/demo",
                        json={},
                        headers={"Origin": "https://foreign.invalid"},
                    ).status_code
                    == 403
                )
                assert client.post("/api/auth/demo", json={}).status_code == 200
                config = client.get("/api/public/config/systematic").json()
                session = client.post(
                    "/api/public/session",
                    json={
                        "source_page": origin
                        + "/demo?utm_source=acceptance&utm_campaign=local"
                    },
                ).json()
                headers = {"Authorization": "Bearer " + session["token"]}
                chat = {
                    "message": "What services do you offer?",
                    "request_id": "smoke-message",
                }
                reply = client.post("/api/public/chat", json=chat, headers=headers)
                assert reply.status_code == 200
                assert (
                    client.post("/api/public/chat", json=chat, headers=headers).json()
                    == reply.json()
                )
                checks.append(
                    "authentication, origin guard, visitor chat and idempotency"
                )
                form = {
                    "name": "QA Test Visitor",
                    "email": "qa-test@example.com",
                    "service": config["services"][0],
                    "confirmed": True,
                    "consent": False,
                }
                request = client.post(
                    "/api/public/requests",
                    json={**form, "kind": "proposal", "request_id": "smoke-proposal"},
                    headers=headers,
                )
                assert request.status_code == 200
                request_id, lead_id = request.json()["id"], request.json()["lead_id"]
                edited = client.patch(
                    "/api/admin/requests/" + request_id,
                    json={
                        "expected_version": 0,
                        "status": "in_progress",
                        "owner": "QA operator",
                        "note": "Isolated acceptance check",
                    },
                )
                assert edited.status_code == 200
                day = datetime.now(timezone.utc).date() + timedelta(days=2)
                while day.weekday() >= 5:
                    day += timedelta(days=1)
                slots = client.get(
                    "/api/public/availability",
                    params={"day": day.isoformat()},
                    headers=headers,
                ).json()["slots"]
                assert slots, "No demo slots available"
                booked = client.post(
                    "/api/public/book",
                    json={**form, "offer_id": slots[0]["id"]},
                    headers=headers,
                )
                assert (
                    booked.status_code == 200 and booked.json()["status"] == "simulated"
                )
                checks.append(
                    "proposal capture, request assignment and simulated booking"
                )
                worker = subprocess.Popen(
                    [sys.executable, "-m", "workspace.worker"],
                    cwd=ROOT,
                    env=env,
                    stdout=log,
                    stderr=log,
                    creationflags=flags,
                )
                for _ in range(30):
                    jobs = client.get("/api/admin/workspace").json()["jobs"]
                    if jobs and all(j["status"] == "simulated" for j in jobs):
                        break
                    time.sleep(0.3)
                assert jobs and all(j["status"] == "simulated" for j in jobs)
                stop(worker)
                checks.append(
                    "separate worker processes jobs without external delivery"
                )
                report = client.get("/api/admin/insights?days=14").json()
                source = next(
                    r for r in report["sources"] if r["source"] == "acceptance"
                )
                assert source["contactable"] == source["booked"] == 1
                stop(api_process)
                api_process = start()
                workspace = client.get("/api/admin/workspace").json()
                assert any(l["id"] == lead_id for l in workspace["leads"])
                assert any(
                    r["id"] == request_id and r["owner"] == "QA operator"
                    for r in workspace["requests"]
                )
                checks.append("source reporting and persistence across API restart")
            (folder / "result.json").write_text(
                json.dumps({"status": "passed", "checks": checks}, indent=2),
                encoding="utf-8",
            )
            print(json.dumps({"status": "passed", "checks": checks, "report": str(folder / "result.json")}), flush=True)
        finally:
            stop(worker)
            stop(api_process)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
