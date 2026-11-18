from datetime import datetime, timedelta, timezone

from test_workspace_runtime import app, client, login, visitor
from workspace.reporting import capture_source, summarize


def test_parallel_request_edits_have_one_winner(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    _, _, receipt = make_request(client)
    login(client)
    barrier = Barrier(2)

    def edit(owner):
        barrier.wait(timeout=10)
        return client.patch(
            "/api/admin/requests/" + receipt["id"],
            json={"expected_version": 0, "status": "in_progress", "owner": owner},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(edit, ["Operator A", "Operator B"])) == [200, 409]


def test_reporting_does_not_inflate_conversion_with_incomplete_legacy_records():
    now = datetime.now(timezone.utc)
    conversations = [
        {"id": key, "created_at": now.isoformat()} for key in ("booked", "anonymous")
    ]
    result = summarize(
        conversations,
        [{"conversation_id": "anonymous", "stage": "won"}],
        [{"conversation_id": "booked", "status": "booked"}],
        [],
        7,
        now,
    )
    assert result["counts"]["engaged"] == 2
    assert result["counts"]["won"] == 0
    assert result["rates"]["booking"] == 50
    assert result["rates"]["won"] is None


def make_request(client, email="returning@example.com", business="systematic"):
    headers, conversation_id = visitor(client, business)
    body = {
        "kind": "proposal",
        "confirmed": True,
        "name": "Returning Visitor",
        "email": email,
        "service": "SEO",
        "goal": "Improve inbound inquiries",
        "request_id": "sales-desk-request",
    }
    response = client.post("/api/public/requests", json=body, headers=headers)
    assert response.status_code == 200
    return headers, body, response.json()


def test_request_workflow_rejects_stale_edits_and_keeps_internal_notes_private(
    client, app
):
    headers, body, receipt = make_request(client)
    endpoint = "/api/admin/requests/" + receipt["id"]
    assert client.patch(endpoint, json={}).status_code == 401
    login(client)
    patch = {
        "expected_version": 0,
        "status": "in_progress",
        "owner": "Ayesha",
        "due_at": "2026-10-05T10:00:00+05:00",
        "note": "Private assessment for the sales team",
    }
    updated = client.patch(endpoint, json=patch)
    assert updated.status_code == 200
    assert updated.json()["version"] == 1
    assert updated.json()["history"][0]["actor"] == "Demo operator"
    assert (
        client.patch(endpoint, json={**patch, "owner": "Different owner"}).status_code
        == 409
    )
    assert (
        client.post("/api/public/requests", json=body, headers=headers).json()
        == receipt
    )
    assert (
        client.patch(
            endpoint,
            json={**patch, "expected_version": 1, "status": "completed", "note": ""},
        ).status_code
        == 422
    )
    finished = client.patch(
        endpoint,
        json={
            **patch,
            "expected_version": 1,
            "status": "completed",
            "note": "Proposal delivered separately",
        },
    )
    assert finished.status_code == 200 and finished.json()["completed_at"]
    assert len(finished.json()["history"]) == 2
    reopened = client.patch(
        endpoint, json={**patch, "expected_version": 2, "status": "recorded"}
    )
    assert reopened.status_code == 200 and reopened.json()["completed_at"] is None
    login(client, "second")
    assert (
        client.patch(endpoint, json={**patch, "expected_version": 3}).status_code == 404
    )


def test_request_owner_and_due_date_validation(client):
    _, _, receipt = make_request(client)
    login(client)
    endpoint = "/api/admin/requests/" + receipt["id"]
    base = {"expected_version": 0, "status": "in_progress", "owner": ""}
    assert client.patch(endpoint, json=base).status_code == 422
    assert (
        client.patch(
            endpoint, json={**base, "owner": "Team", "due_at": "2026-10-05T10:00:00"}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            endpoint, json={**base, "owner": "Team", "status": "sent"}
        ).status_code
        == 422
    )


def test_related_inquiries_are_admin_only_tenant_scoped_and_do_not_merge(client, app):
    h, _, first = make_request(client)
    _, _, second = make_request(client, "RETURNING@example.com")
    _, _, foreign = make_request(client, business="second")
    endpoint = "/api/admin/leads/" + first["lead_id"] + "/related"
    assert client.get(endpoint, headers=h).status_code == 401
    login(client)
    response = client.get(endpoint).json()
    assert [row["id"] for row in response["matches"]] == [second["lead_id"]]
    assert response["basis"] == "same_email_unverified"
    assert first["lead_id"] != second["lead_id"]
    public = client.get("/api/public/conversation", headers=h).json()
    assert public["id"] == first["conversation_id"]
    assert "matches" not in public
    login(client, "second")
    assert client.get(endpoint).status_code == 404


def test_source_capture_keeps_approved_campaign_fields_only(client, app):
    website = app.state.db.get("systematic", "business", "systematic")[
        "website"
    ].rstrip("/")
    url = (
        website
        + "/seo?utm_source=google&utm_medium=cpc&utm_campaign=autumn&token=private&email=person@example.com#secret"
    )
    response = client.post("/api/public/session", json={"source_page": url}).json()
    conv = app.state.db.get(
        "systematic", "conversation", response["conversation"]["id"]
    )
    assert conv["source_page"] == website + "/seo"
    assert conv["attribution"] == {
        "utm_source": "google",
        "utm_medium": "cpc",
        "utm_campaign": "autumn",
    }
    assert "private" not in str(conv) and "person@example.com" not in str(conv)
    assert capture_source(
        "https://evil.example/?utm_source=fake", website, [website]
    ) == (website, {})
    assert (
        capture_source(website + "/?utm_source=person@example.com", website, [website])[
            1
        ]
        == {}
    )


def test_insights_counts_sessions_once_and_uses_consistent_cohort():
    now = datetime(2026, 10, 4, tzinfo=timezone.utc)

    def conv(key, age, messages=None):
        return {
            "id": key,
            "created_at": (now - timedelta(days=age)).isoformat(),
            "messages": messages or [],
            "attribution": {"utm_source": "google"},
        }

    conversations = [
        conv("idle", 1),
        conv("one", 2, [{"role": "user"}]),
        conv("two", 3),
        conv("old", 60),
        conv("future", -1),
    ]
    leads = [
        {"conversation_id": "one", "email": "a@example.com", "stage": "won"},
        {"conversation_id": "one", "email": "a@example.com", "stage": "won"},
        {"conversation_id": "two", "phone": "123", "stage": "contactable"},
        {"conversation_id": "old", "email": "old@example.com", "stage": "won"},
    ]
    meetings = [
        {"conversation_id": "one", "status": "booked"},
        {"conversation_id": "one", "status": "booked"},
        {"conversation_id": "two", "status": "cancelled"},
    ]
    requests = [
        {
            "conversation_id": "two",
            "status": "in_progress",
            "due_at": (now - timedelta(hours=1)).isoformat(),
        },
        {
            "conversation_id": "one",
            "status": "completed",
            "due_at": (now - timedelta(hours=1)).isoformat(),
        },
    ]
    result = summarize(conversations, leads, meetings, requests, 14, now)
    assert result["counts"] == {
        "sessions": 3,
        "engaged": 2,
        "contactable": 2,
        "progressing": 1,
        "booked": 1,
        "won": 1,
    }
    assert result["rates"] == {"contact_capture": 100.0, "booking": 50.0, "won": 50.0}
    assert result["open_requests"] == result["overdue_requests"] == 1
    assert result["sources"][0]["engaged"] == 2
    assert all(v is None for v in summarize([], [], [], [], 7, now)["rates"].values())


def test_insights_uses_full_history_not_workspace_preview_and_is_tenant_scoped(
    client, app
):
    assert client.get("/api/admin/insights").status_code == 401
    login(client, "second")
    with app.state.db.transaction("second") as c:
        for i in range(205):
            key = f"analytics-{i}"
            app.state.db.put(
                "second",
                "conversation",
                key,
                {
                    "id": key,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "messages": [{"role": "user"}],
                },
                c,
            )
    assert client.get("/api/admin/insights?days=7").json()["counts"]["engaged"] == 205
    assert client.get("/api/admin/insights?days=8").status_code == 422
    login(client)
    assert client.get("/api/admin/insights?days=7").json()["counts"]["engaged"] < 205
