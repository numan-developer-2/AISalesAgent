"""Setup contracts tested with local fixtures; no browser or Google calls."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "authorize_workspace", ROOT / "scripts/google/authorize_workspace.py"
)
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


@pytest.mark.parametrize("service", ["calendar", "sheets"])
def test_oauth_setup_requests_correct_scopes_and_preserves_existing_token(
    tmp_path, monkeypatch, service
):
    client = tmp_path / "client.json"
    client.write_text(json.dumps({"installed": {"client_id": "test-only"}}))
    token = tmp_path / "token.json"
    credentials = SimpleNamespace(
        refresh_token="fake-refresh",
        has_scopes=lambda scopes: scopes == setup.SCOPES[service],
        to_json=lambda: json.dumps({"refresh_token": "fake-refresh"}),
    )
    factory = Mock(
        return_value=SimpleNamespace(run_local_server=Mock(return_value=credentials))
    )
    monkeypatch.setattr(
        "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file", factory
    )
    setup.authorize(service, client, token)
    factory.assert_called_once_with(str(client.resolve()), scopes=setup.SCOPES[service])
    assert json.loads(token.read_text())["refresh_token"] == "fake-refresh"
    with pytest.raises(ValueError, match="already exists"):
        setup.authorize(service, client, token)
    assert factory.call_count == 1
    setup.authorize(service, client, token, replace=True)
    assert factory.call_count == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == ["client.json", "token.json"]


def test_oauth_setup_rejects_missing_offline_access(tmp_path, monkeypatch):
    client, token = tmp_path / "client.json", tmp_path / "token.json"
    client.write_text('{"installed": {}}')
    monkeypatch.setattr(
        "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
        Mock(
            return_value=SimpleNamespace(
                run_local_server=lambda **kwargs: SimpleNamespace(refresh_token=None)
            )
        ),
    )
    with pytest.raises(ValueError, match="offline access"):
        setup.authorize("sheets", client, token)
    assert not token.exists()


def test_calendar_auth_rejects_token_with_missing_scopes(tmp_path, monkeypatch):
    from integrations.google_calendar.auth import load_authorized_credentials
    from integrations.google_calendar.errors import CalendarAuthenticationRequired

    token = tmp_path / "token.json"
    token.write_text("{}")
    monkeypatch.setattr(
        "integrations.google_calendar.auth.Credentials.from_authorized_user_file",
        Mock(return_value=SimpleNamespace(valid=True, has_scopes=lambda scopes: False)),
    )
    with pytest.raises(CalendarAuthenticationRequired, match="scopes"):
        load_authorized_credentials(token)


def test_calendar_refresh_works_with_readonly_secret_mount(tmp_path, monkeypatch):
    import errno
    from integrations.google_calendar.auth import load_authorized_credentials

    token = tmp_path / "token.json"
    token.write_text("original private token")
    credentials = SimpleNamespace(
        valid=False,
        expired=True,
        refresh_token="fake-refresh",
        has_scopes=lambda scopes: True,
        refresh=Mock(),
        to_json=lambda: "updated token",
    )
    monkeypatch.setattr(
        "integrations.google_calendar.auth.Credentials.from_authorized_user_file",
        Mock(return_value=credentials),
    )
    monkeypatch.setattr(
        "integrations.google_calendar.auth.tempfile.NamedTemporaryFile",
        Mock(side_effect=OSError(errno.EROFS, "Read-only secret mount")),
    )
    assert load_authorized_credentials(token) is credentials
    credentials.refresh.assert_called_once()
    assert token.read_text() == "original private token"
