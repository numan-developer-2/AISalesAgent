from __future__ import annotations

import json
import hashlib
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from workspace.api import create_app
from workspace.config import Settings, ROOT
from workspace.database import Database, jobs
from sqlalchemy import update
from workspace.worker import process_one
from tools.confirmation import looks_explicit_confirmation
from tools.repository import _action_from_record

HEADERS = {"X-Workspace-Request": "1", "Origin": "http://localhost:5173"}


@pytest.fixture
def app(tmp_path, monkeypatch):
    config_dir = tmp_path / "businesses"
    config_dir.mkdir()
    original = json.loads(
        (ROOT / "config/businesses/systematic.json").read_text(encoding="utf-8")
    )
    original.pop("knowledge_directory", None)
    for tenant, name in [
        ("systematic", "Systematic Demo Studio"),
        ("second", "Second Business"),
    ]:
        config = {**original, "id": tenant, "name": name}
        (config_dir / (tenant + ".json")).write_text(
            json.dumps(config), encoding="utf-8"
        )
    monkeypatch.setenv("BUSINESS_CONFIG_DIR", str(config_dir))
    return create_app(
        Settings(
            mode="demo", database_url="sqlite:///" + (tmp_path / "test.db").as_posix()
        )
    )


@pytest.fixture
def client(app):
    with TestClient(app, headers=HEADERS) as c:
        yield c


def visitor(client, business="systematic"):
    response = client.post("/api/public/session", json={"business": business})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}, response.json()[
        "conversation"
    ]["id"]


def login(client, business="systematic"):
    response = client.post("/api/auth/demo", json={"business": business})
    assert response.status_code == 200


def next_weekday():
    day = datetime.now(timezone.utc).date() + timedelta(days=2)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.isoformat()


def test_admin_auth_origin_and_public_config(client):
    assert client.get("/api/admin/workspace").status_code == 401
    assert (
        client.post(
            "/api/auth/demo", json={}, headers={"Origin": "https://attacker.example"}
        ).status_code
        == 403
    )
    config = client.get("/api/public/config/systematic").json()
    assert "knowledge_directory" not in config and "notification_email" not in config
    login(client)
    assert client.get("/api/admin/workspace").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/admin/workspace").status_code == 401


def test_chat_persists_idempotently_and_tenant_isolation(client, app):
    h, conv = visitor(client)
    body = {
        "message": "I need SEO. My email is alex@example.com",
        "request_id": "request-123456",
    }
    first = client.post("/api/public/chat", json=body, headers=h)
    assert first.status_code == 200, first.text
    again = client.post("/api/public/chat", json=body, headers=h)
    assert again.json() == first.json()
    assert (
        len(client.get("/api/public/conversation", headers=h).json()["messages"]) == 2
    )
    login(client, "second")
    assert client.get("/api/admin/conversations/" + conv).status_code == 404
    assert all(
        l.get("email") != "alex@example.com"
        for l in client.get("/api/admin/workspace").json()["leads"]
    )
    persisted = Database(app.state.settings.database_url)
    assert (
        persisted.get("systematic", "conversation", conv)["messages"][0]["content"]
        == body["message"]
    )


def test_booking_confirmation_offer_ownership_and_idempotency(client, app):
    h, conv = visitor(client)
    result = client.get("/api/public/availability?day=" + next_weekday(), headers=h)
    assert result.status_code == 200, result.text
    slot = result.json()["slots"][0]
    body = {
        "name": "Alex Guest",
        "email": "alex@example.com",
        "company": "Example",
        "service": "SEO",
        "goal": "Improve local visibility",
        "consent": True,
        "offer_id": slot["id"],
        "confirmed": False,
    }
    assert client.post("/api/public/book", json=body, headers=h).status_code == 422
    for value in [1, "true", None]:
        assert (
            client.post(
                "/api/public/book", json={**body, "confirmed": value}, headers=h
            ).status_code
            == 422
        )
    other, _ = visitor(client)
    body["confirmed"] = True
    assert client.post("/api/public/book", json=body, headers=other).status_code == 404
    first = client.post("/api/public/book", json=body, headers=h)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "simulated"
    assert (
        client.post("/api/public/book", json=body, headers=h).json()["id"]
        == first.json()["id"]
    )
    assert (
        len(
            [
                m
                for m in app.state.db.list("systematic", "meeting")
                if m.get("conversation_id") == conv
            ]
        )
        == 1
    )
    lead = app.state.db.get("systematic", "lead", first.json()["lead_id"])
    assert lead["stage"] == "meeting_booked"
    assert app.state.db.list_jobs("systematic")


def test_expired_offer_rejected(client, app):
    h, _ = visitor(client)
    slot = client.get(
        "/api/public/availability?day=" + next_weekday(), headers=h
    ).json()["slots"][0]
    slot["expires"] = 0
    app.state.db.put("systematic", "offer", slot["id"], slot)
    response = client.post(
        "/api/public/book",
        headers=h,
        json={
            "name": "Alex",
            "email": "a@example.com",
            "service": "SEO",
            "offer_id": slot["id"],
            "confirmed": True,
        },
    )
    assert response.status_code == 409


def test_handover_human_reply_and_ai_pause(client):
    h, conv = visitor(client)
    response = client.post(
        "/api/public/requests",
        headers=h,
        json={
            "kind": "handover",
            "name": "Alex",
            "email": "a@example.com",
            "service": "SEO",
            "confirmed": True,
        },
    )
    assert response.status_code == 200, response.text
    login(client)
    assert (
        client.post("/api/admin/conversations/" + conv + "/takeover").json()["status"]
        == "human"
    )
    reply = client.post(
        "/api/admin/conversations/" + conv + "/reply",
        json={"message": "Hello, Alex. How can I help?"},
    )
    assert reply.status_code == 200
    result = client.post(
        "/api/public/chat",
        headers=h,
        json={"message": "Thanks, I need help", "request_id": "human-request-123"},
    )
    assert result.status_code == 200, result.text
    assert result.json()["conversation"]["messages"][-1]["role"] == "user"
    assert any(
        m.get("author") == "Sales team"
        for m in client.get("/api/public/conversation", headers=h).json()["messages"]
    )


def test_durable_worker_claims_once_and_marks_demo(client, app):
    db = app.state.db
    with db.transaction() as c:
        for _ in range(2):
            db.enqueue(
                "systematic", "email", "same-event", {"lead_id": "sample-0"}, conn=c
            )
    assert len(db.list_jobs("systematic")) == 1
    reloaded = Database(app.state.settings.database_url)
    assert process_one(reloaded, app.state.settings)
    assert db.list_jobs("systematic")[0]["status"] == "simulated"
    assert not process_one(reloaded, app.state.settings)


def test_followup_excludes_closed_lead(client, app):
    app.state.db.enqueue(
        "systematic", "followup", "followup-closed", {"lead_id": "sample-6"}
    )
    process_one(app.state.db, app.state.settings)
    assert app.state.db.list_jobs("systematic")[0]["status"] == "cancelled"


def test_lead_outcome_knowledge_and_settings_are_scoped(client):
    login(client)
    assert (
        client.patch("/api/admin/leads/sample-0", json={"stage": "lost"}).status_code
        == 422
    )
    result = client.patch(
        "/api/admin/leads/sample-0",
        json={
            "stage": "lost",
            "lost_reason": "Not a service fit",
            "note": "Follow-up complete",
        },
    )
    assert result.status_code == 200
    assert result.json()["notes"][-1]["text"] == "Follow-up complete"
    doc = client.post(
        "/api/admin/knowledge",
        json={
            "title": "Example FAQ",
            "content": "This answer is approved for the Systematic workspace.",
        },
    )
    assert doc.status_code == 200
    key = doc.json()["id"]
    assert (
        client.patch(
            "/api/admin/settings",
            json={"qualification": {"hot_threshold": 20, "warm_threshold": 40}},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            "/api/admin/settings", json={"knowledge_directory": "../../config"}
        ).status_code
        == 422
    )
    login(client, "second")
    assert client.delete("/api/admin/knowledge/" + key).status_code == 404


@pytest.mark.parametrize(
    "text",
    [
        "do not book this",
        "no, please book nothing",
        "don't confirm",
        "yesterday",
        "can you confirm?",
        "not confirmed",
    ],
)
def test_negative_booking_language_is_not_confirmation(text):
    assert not looks_explicit_confirmation(text)


def test_database_action_expiry_is_datetime():
    action = _action_from_record(
        {
            "action_type": "book_meeting",
            "conversation_id": "c",
            "idempotency_key": "key",
            "expires_at": "2026-09-20T10:00:00Z",
        }
    )
    assert isinstance(action.expires_at, datetime)
    assert action.expires_at < datetime(2026, 10, 1, tzinfo=timezone.utc)


def test_demo_processing_cannot_consume_another_business_job(client, app):
    db = app.state.db
    db.enqueue("second", "email", "second-job", {"lead_id": "missing"})
    db.enqueue("systematic", "email", "own-job", {"lead_id": "sample-0"})
    login(client)
    assert client.post("/api/admin/jobs/demo-process").json()["processed"] == 1
    assert db.list_jobs("second")[0]["status"] == "pending"
    assert db.list_jobs("systematic")[0]["status"] == "simulated"
    assert db.list("second", "lead") == []


def test_expired_lease_recovery_rejects_stale_worker_completion(app):
    db = app.state.db
    db.enqueue("systematic", "email", "lease-test", {"lead_id": "sample-0"})
    original = db.claim_job()
    assert db.claim_job() is None
    with db.transaction() as conn:
        conn.execute(
            update(jobs)
            .where(jobs.c.id == original["id"])
            .values(lease_until=time.time() - 1)
        )
    recovered = db.claim_job()
    assert recovered["attempts"] == 2
    db.finish_job(original, "completed")
    assert db.list_jobs("systematic")[0]["status"] == "running"
    db.finish_job(recovered, "simulated")
    assert db.list_jobs("systematic")[0]["status"] == "simulated"


def test_worker_retries_then_fails_without_persisting_provider_details(
    app, monkeypatch
):
    def fail(*args):
        raise RuntimeError("private-provider-response")

    monkeypatch.setattr("workspace.worker.deliver", fail)
    db = app.state.db
    db.enqueue("systematic", "email", "retry-test", {"lead_id": "sample-0"})
    for attempt in range(1, 6):
        assert process_one(db, app.state.settings)
        job = db.list_jobs("systematic")[0]
        assert job["attempts"] == attempt
        assert job["status"] == ("failed" if attempt == 5 else "pending")
        assert "private-provider-response" not in job["error"]
        assert job["due"] > time.time()
        with db.transaction() as conn:
            conn.execute(
                update(jobs).where(jobs.c.id == job["id"]).values(due=time.time() - 1)
            )
    assert not process_one(db, app.state.settings)


def test_live_worker_missing_configuration_is_blocked(app):
    app.state.settings.mode = "live"
    app.state.settings.env = {}
    app.state.db.enqueue("systematic", "email", "blocked-test", {"lead_id": "sample-0"})
    assert process_one(app.state.db, app.state.settings)
    assert app.state.db.list_jobs("systematic")[0]["status"] == "blocked"


@pytest.mark.parametrize("outcome", ["found", "missing", "unavailable"])
def test_ambiguous_calendar_booking_reconciles_safely(
    client, app, monkeypatch, outcome
):
    headers, conv_id = visitor(client)
    slot = client.get(
        "/api/public/availability?day=" + next_weekday(), headers=headers
    ).json()["slots"][0]
    login(client)
    app.state.settings.mode = "live"
    app.state.settings.env = {
        "GOOGLE_CALENDAR_TOKEN_FILE": "test-token",
        "GOOGLE_CALENDAR_ID": "test-calendar",
    }
    db = app.state.db
    business = db.get("systematic", "business", "systematic")
    business["integrations"]["calendar"] = True
    db.put("systematic", "business", "systematic", business)
    gateway = Mock()
    gateway.config.calendar_id = "test-calendar"
    gateway.slot_is_free.return_value = True
    gateway.service.events.return_value.insert.return_value.execute.side_effect = (
        TimeoutError()
    )
    lookup = gateway.service.events.return_value.get.return_value.execute
    if outcome == "found":
        lookup.return_value = {
            "status": "confirmed",
            "htmlLink": "https://calendar.example/event",
        }
    else:
        error = RuntimeError("provider details must stay private")
        error.resp = SimpleNamespace(status=404 if outcome == "missing" else 503)
        lookup.side_effect = error
    monkeypatch.setattr(
        "integrations.google_calendar.gateway.GoogleCalendarGateway",
        lambda *a, **k: gateway,
    )
    body = {
        "name": "Alex",
        "email": "alex@example.com",
        "service": "SEO",
        "offer_id": slot["id"],
        "confirmed": True,
    }
    assert (
        client.post("/api/public/book", headers=headers, json=body).status_code == 503
    )
    key = hashlib.sha256(slot["start_at"].encode()).hexdigest()
    reservation = db.get("systematic", "reservation", key)
    assert reservation["status"] == "needs_review"
    assert db.get("systematic", "meeting", slot["id"]) is None
    endpoint = "/api/admin/bookings/" + slot["id"] + "/reconcile"
    assert client.post(endpoint).status_code == 409
    reservation["created"] = time.time() - 121
    db.put("systematic", "reservation", key, reservation)
    saved_lead = {
        **reservation["lead"],
        "notes": [{"text": "Operator checked the inquiry"}],
    }
    db.put("systematic", "lead", saved_lead["id"], saved_lead)
    response = client.post(endpoint)
    if outcome == "found":
        assert response.json()["status"] == "booked"
        assert db.get("systematic", "meeting", slot["id"])["status"] == "booked"
        assert (
            db.get("systematic", "lead", saved_lead["id"])["notes"]
            == saved_lead["notes"]
        )
        assert (
            db.get("systematic", "conversation", conv_id)["lead_id"]
            == reservation["lead"]["id"]
        )
        assert len(db.list_jobs("systematic")) == 1
        assert client.post(endpoint).status_code == 409
        assert len(db.list_jobs("systematic")) == 1
    elif outcome == "missing":
        assert response.json()["status"] == "released"
        assert db.get("systematic", "reservation", key) is None
    else:
        assert response.status_code == 503
        assert "provider details" not in response.text
        assert db.get("systematic", "reservation", key)["status"] == "needs_review"
    gateway.service.events.return_value.insert.assert_called_once()


@pytest.mark.parametrize("failure", [None, "availability", "insertion"])
def test_real_calendar_contract_and_failure_boundaries(
    client, app, monkeypatch, failure
):
    from integrations.google_calendar.gateway import GoogleCalendarGateway

    h, conv_id = visitor(client)
    chat = client.post(
        "/api/public/chat",
        headers=h,
        json={
            "message": "SEO for alex@example.com",
            "request_id": "calendar-contract-01",
        },
    ).json()
    lead_id = chat["conversation"]["lead_id"]
    slot = client.get(
        "/api/public/availability?day=" + next_weekday(), headers=h
    ).json()["slots"][0]
    app.state.settings.mode = "live"
    app.state.settings.env = {
        "GOOGLE_CALENDAR_TOKEN_FILE": "unused-test-token",
        "GOOGLE_CALENDAR_ID": "test-calendar",
    }
    db = app.state.db
    b = db.get("systematic", "business", "systematic")
    b["integrations"]["calendar"] = True
    db.put("systematic", "business", "systematic", b)
    service = Mock()
    service.freebusy.return_value.query.return_value.execute.return_value = {
        "calendars": {"test-calendar": {"busy": []}}
    }
    if failure == "availability":
        service.freebusy.return_value.query.return_value.execute.side_effect = (
            TimeoutError()
        )

    def insertion():
        if failure == "insertion":
            raise TimeoutError()
        # A sales rep can work while Google is processing the insertion.
        with db.transaction("systematic") as c:
            conv = db.get("systematic", "conversation", conv_id, c)
            conv["status"] = "human"
            conv["messages"].append(
                {
                    "id": "human-concurrent",
                    "role": "assistant",
                    "author": "Sales team",
                    "content": "I joined during booking",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            lead = db.get("systematic", "lead", lead_id, c)
            lead["notes"] = [{"text": "Preserve this operator note"}]
            db.put("systematic", "conversation", conv_id, conv, c)
            db.put("systematic", "lead", lead_id, lead, c)
        return {"id": "test-event"}

    service.events.return_value.insert.return_value.execute.side_effect = insertion

    def gateway(config, schedule):
        return GoogleCalendarGateway(config=config, service=service, schedule=schedule)

    monkeypatch.setattr(
        "integrations.google_calendar.gateway.GoogleCalendarGateway", gateway
    )
    response = client.post(
        "/api/public/book",
        headers=h,
        json={
            "name": "Alex",
            "email": "alex@example.com",
            "service": "SEO",
            "offer_id": slot["id"],
            "confirmed": True,
        },
    )
    assert (
        service.freebusy.return_value.query.call_args.kwargs["body"]["timeZone"]
        == b["timezone"]
    )
    if failure:
        assert response.status_code == 503
        reservations = db.list("systematic", "reservation")
        if failure == "availability":
            assert reservations == []
            service.events.return_value.insert.assert_not_called()
        else:
            assert reservations[0]["status"] == "needs_review"
    else:
        assert response.status_code == 200, response.text
        conv = db.get("systematic", "conversation", conv_id)
        assert conv["status"] == "human"
        assert any(m["id"] == "human-concurrent" for m in conv["messages"])
        assert (
            db.get("systematic", "lead", lead_id)["notes"][0]["text"]
            == "Preserve this operator note"
        )


def test_concurrent_request_retries_and_revised_submission(client, app):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    h, conv_id = visitor(client)
    body = {
        "name": "Alex",
        "email": "alex@example.com",
        "service": "SEO",
        "goal": "Initial requirements",
        "kind": "proposal",
        "confirmed": True,
        "request_id": "proposal-request-1",
    }
    barrier = Barrier(2)

    def submit():
        barrier.wait(timeout=10)
        return client.post("/api/public/requests", headers=h, json=body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: submit(), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    db = app.state.db
    assert (
        len(
            [
                l
                for l in db.list("systematic", "lead")
                if l.get("conversation_id") == conv_id
            ]
        )
        == 1
    )
    assert len(db.list_jobs("systematic")) == 1
    edited = {**body, "goal": "Revised scope", "consent": True}
    assert (
        client.post("/api/public/requests", headers=h, json=edited).status_code == 409
    )
    result = client.post(
        "/api/public/requests",
        headers=h,
        json={**edited, "request_id": "proposal-request-2"},
    )
    assert result.status_code == 200
    lead = db.get("systematic", "lead", result.json()["lead_id"])
    assert lead["business_goal"] == "Revised scope"
    assert lead["consent_status"] == "granted"
    assert len(db.list("systematic", "consent_event")) == 1


def test_optout_is_independent_of_model_and_suppresses_new_conversation(
    client, app, monkeypatch
):
    h, _ = visitor(client)
    form = {
        "name": "Alex",
        "email": "alex@example.com",
        "service": "SEO",
        "kind": "proposal",
        "consent": True,
        "confirmed": True,
    }
    first = client.post("/api/public/requests", headers=h, json=form).json()
    assert any(j["kind"] == "followup" for j in app.state.db.list_jobs("systematic"))
    model = Mock(side_effect=RuntimeError("provider unavailable"))
    monkeypatch.setattr("workspace.api.respond", model)
    response = client.post(
        "/api/public/chat",
        headers=h,
        json={"message": "unsubscribe", "request_id": "unsubscribe-request"},
    )
    assert response.status_code == 200
    model.assert_not_called()
    db = app.state.db
    assert (
        db.get("systematic", "lead", first["lead_id"])["consent_status"] == "declined"
    )
    assert all(
        j["status"] == "cancelled"
        for j in db.list_jobs("systematic")
        if j["kind"] == "followup"
    )
    second, _ = visitor(client)
    again = client.post("/api/public/requests", headers=second, json=form).json()
    assert (
        db.get("systematic", "lead", again["lead_id"])["consent_status"] == "declined"
    )


def test_admin_edits_enqueue_sync_and_preserve_tenant_scope(client, app):
    db = app.state.db
    b = db.get("systematic", "business", "systematic")
    b["integrations"].update(sheets=True, crm=True)
    db.put("systematic", "business", "systematic", b)
    login(client)
    result = client.patch(
        "/api/admin/leads/sample-0", json={"stage": "won", "consent_status": "declined"}
    )
    assert result.status_code == 200
    assert {j["kind"] for j in db.list_jobs("systematic")} == {"crm", "sheets"}
    assert len(db.list("systematic", "lead_event")) == 1
    assert db.list_jobs("second") == []
    assert db.list("second", "consent_event") == []


@pytest.mark.parametrize(
    "body",
    [
        {"services": "SEO"},
        {"qualification": None},
        {"navigation": ["bad"]},
        {"integrations": None},
        {"services": ["SEO", "seo"]},
        {"qualification": {"hot_threshold": "70"}},
        {"followup_hours": True},
        {"notification_email": "not-an-email"},
        {"allowed_origins": ["https://example.com?bad=1"]},
        {"working_hours": {"duration": 0}},
        {"timezone": "not-a-timezone"},
    ],
)
def test_settings_reject_invalid_nested_types_without_corrupting_business(
    client, app, body
):
    login(client)
    old = app.state.db.get("systematic", "business", "systematic")
    assert client.patch("/api/admin/settings", json=body).status_code == 422
    assert app.state.db.get("systematic", "business", "systematic") == old


def test_chat_rejects_changed_payload_for_same_request_id(client):
    h, _ = visitor(client)
    body = {"message": "I need SEO", "request_id": "stable-message-key"}
    first = client.post("/api/public/chat", headers=h, json=body)
    assert first.status_code == 200
    assert client.post("/api/public/chat", headers=h, json=body).json() == first.json()
    assert (
        client.post(
            "/api/public/chat", headers=h, json={**body, "message": "Different intent"}
        ).status_code
        == 409
    )


def test_budget_normalization_and_negated_authority(app):
    from workspace.engine import merge_lead
    from workspace.qualification import minimum_stated_usd, has_decision_authority

    assert minimum_stated_usd("$1.5k") == minimum_stated_usd("USD 1,500") == 1500
    assert minimum_stated_usd("$500 - $1,500") == 500
    assert minimum_stated_usd("$500 monthly for 12 months") == 500
    assert minimum_stated_usd("USD 1.5k monthly, 12 month contract") == 1500
    assert minimum_stated_usd("500-1,500 USD") == 500
    assert minimum_stated_usd("up to $1500") is None
    assert minimum_stated_usd("PKR 150,000") is None
    assert not has_decision_authority("Not the decision maker")
    assert not has_decision_authority("non-owner")
    assert has_decision_authority("Business owner")
    b = app.state.db.get("systematic", "business", "systematic")
    lead = merge_lead(
        None, {"budget_range": "$1.5k", "authority_status": "Not the decision maker"}, b
    )
    assert (
        next(
            r["score"]
            for r in lead["score_reasons"]
            if r["component"] == "budget_authority"
        )
        == 10
    )


@pytest.mark.parametrize("consent", ["true", "false", 1, None])
def test_form_consent_requires_boolean(client, consent):
    headers, _ = visitor(client)
    response = client.post(
        "/api/public/requests",
        headers=headers,
        json={
            "kind": "proposal",
            "confirmed": True,
            "name": "Alex Guest",
            "email": "alex@example.com",
            "service": "SEO",
            "consent": consent,
        },
    )
    assert response.status_code == 422
