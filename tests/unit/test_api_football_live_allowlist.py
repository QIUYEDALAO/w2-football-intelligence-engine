from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from w2.providers.api_football import ApiFootballClient, LiveNetworkDisabledError
from w2.providers.control import ProviderCallsDisabledError


@pytest.mark.parametrize("configured", [None, "", "invalid", "TRUE-ish"])
def test_api_football_global_provider_switch_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    configured: str | None,
) -> None:
    if configured is None:
        monkeypatch.delenv("W2_PROVIDER_CALLS_DISABLED", raising=False)
    else:
        monkeypatch.setenv("W2_PROVIDER_CALLS_DISABLED", configured)
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "status")
    client = ApiFootballClient(
        allow_live=True,
        allowed_live_endpoints=frozenset({"status"}),
    )

    with pytest.raises(ProviderCallsDisabledError, match="PROVIDER_CALLS_DISABLED"):
        client.request_live("status", {})


def test_api_football_missing_global_endpoint_allowlist_is_empty(monkeypatch) -> None:
    monkeypatch.setenv("W2_PROVIDER_CALLS_DISABLED", "false")
    monkeypatch.delenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", raising=False)
    client = ApiFootballClient(
        allow_live=True,
        allowed_live_endpoints=frozenset({"status"}),
    )

    with pytest.raises(LiveNetworkDisabledError, match="live endpoint not approved: status"):
        client.request_live("status", {})


def test_api_football_live_endpoint_allowlist_blocks_unapproved_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("W2_PROVIDER_CALLS_DISABLED", "false")
    client = ApiFootballClient(
        allow_live=True,
        allowed_live_endpoints=frozenset({"statistics", "lineups", "injuries"}),
    )

    with pytest.raises(LiveNetworkDisabledError, match="live endpoint not approved: odds"):
        client.request_live("odds", {"fixture": "1489404"})


def test_api_football_statistics_uses_fixtures_statistics_http_path(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeResponse:
        status = 200
        headers: dict[str, str] = {}

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"response": []}).encode()

    def fake_urlopen(request: urllib.request.Request, timeout: int) -> FakeResponse:
        captured["url"] = request.full_url
        captured["timeout"] = str(timeout)
        return FakeResponse()

    monkeypatch.setenv("W2_PROVIDER_CALLS_DISABLED", "false")
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "statistics")
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "test-key")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = ApiFootballClient(
        allow_live=True,
        allowed_live_endpoints=frozenset({"statistics"}),
    )

    response = client.request_live("statistics", {"fixture": "1489404"})

    assert response.status_code == 200
    assert captured["url"].endswith("/fixtures/statistics?fixture=1489404")


def test_api_football_request_timeout_is_configurable_and_capped(monkeypatch) -> None:
    captured: dict[str, int] = {}

    class FakeResponse:
        status = 200
        headers: dict[str, str] = {}

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"response": []}'

    def fake_urlopen(request: urllib.request.Request, timeout: int) -> FakeResponse:
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("W2_PROVIDER_CALLS_DISABLED", "false")
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "fixtures")
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "test-key")
    monkeypatch.setenv("W2_PROVIDER_REQUEST_TIMEOUT_SECONDS", "90")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    ApiFootballClient(
        allow_live=True,
        allowed_live_endpoints=frozenset({"fixtures"}),
    ).request_live("fixtures", {"league": "128", "season": "2026"})

    assert captured["timeout"] == 60


def test_api_football_squads_uses_players_squads_http_path(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeResponse:
        status = 200
        headers: dict[str, str] = {}

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"response": []}).encode()

    def fake_urlopen(request: urllib.request.Request, timeout: int) -> FakeResponse:
        captured["url"] = request.full_url
        return FakeResponse()

    monkeypatch.setenv("W2_PROVIDER_CALLS_DISABLED", "false")
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "squads")
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "test-key")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = ApiFootballClient(
        allow_live=True,
        allowed_live_endpoints=frozenset({"squads"}),
    )

    client.request_live("squads", {"team": "1"})

    assert captured["url"].endswith("/players/squads?team=1")


def test_api_football_player_profile_uses_players_http_path(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeResponse:
        status = 200
        headers: dict[str, str] = {}

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"response": []}).encode()

    def fake_urlopen(request: urllib.request.Request, timeout: int) -> FakeResponse:
        captured["url"] = request.full_url
        return FakeResponse()

    monkeypatch.setenv("W2_PROVIDER_CALLS_DISABLED", "false")
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "players")
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "test-key")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = ApiFootballClient(
        allow_live=True,
        allowed_live_endpoints=frozenset({"players"}),
    )

    client.request_live("players", {"id": "100", "season": "2026"})

    assert captured["url"].endswith("/players?id=100&season=2026")


def test_api_football_profiles_uses_players_profiles_http_path(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeResponse:
        status = 200
        headers: dict[str, str] = {}

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"response": []}).encode()

    def fake_urlopen(request: urllib.request.Request, timeout: int) -> FakeResponse:
        captured["url"] = request.full_url
        return FakeResponse()

    monkeypatch.setenv("W2_PROVIDER_CALLS_DISABLED", "false")
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "player_profiles")
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "test-key")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = ApiFootballClient(
        allow_live=True,
        allowed_live_endpoints=frozenset({"player_profiles"}),
    )

    client.request_live("player_profiles", {"player": "100"})

    assert captured["url"].endswith("/players/profiles?player=100")


def test_api_football_provider_calls_disabled_blocks_before_transport(monkeypatch) -> None:
    def forbidden_urlopen(*args: object, **kwargs: object) -> object:  # pragma: no cover
        raise AssertionError("provider transport must not be called")

    monkeypatch.setenv("W2_PROVIDER_CALLS_DISABLED", "true")
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "test-key")
    monkeypatch.setattr(urllib.request, "urlopen", forbidden_urlopen)
    client = ApiFootballClient(
        allow_live=True,
        allowed_live_endpoints=frozenset({"statistics"}),
    )

    with pytest.raises(ProviderCallsDisabledError, match="PROVIDER_CALLS_DISABLED"):
        client.request_live("statistics", {"fixture": "1489404"})


def test_api_football_request_live_records_provider_ledger(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeLedger:
        def record_request(self, **kwargs: object) -> None:
            captured.update(kwargs)

    class FakeResponse:
        status = 200
        headers = {"x-ratelimit-requests-remaining": "6999"}

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"response": []}).encode()

    monkeypatch.setenv("W2_PROVIDER_CALLS_DISABLED", "false")
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "odds")
    monkeypatch.delenv("W2_PROVIDER_REQUEST_LEDGER_ENABLED", raising=False)
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "test-key")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())
    client = ApiFootballClient(
        allow_live=True,
        allowed_live_endpoints=frozenset({"odds"}),
        request_ledger=FakeLedger(),
    )

    response = client.request_live("odds", {"fixture": "1489404"})

    assert response.status_code == 200
    assert captured["provider"] == "api_football"
    assert captured["endpoint"] == "odds"
    assert captured["params"] == {"fixture": "1489404"}
    assert captured["status_code"] == 200
    assert captured["live"] is True


def test_api_football_http_error_records_one_sanitized_ledger_row(monkeypatch) -> None:
    calls = 0
    records: list[dict[str, object]] = []

    class FakeLedger:
        def record_request(self, **kwargs: object) -> None:
            records.append(kwargs)

    def fail_transport(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise urllib.error.HTTPError(
            url="https://example.invalid",
            code=503,
            msg="unavailable",
            hdrs={"x-ratelimit-requests-remaining": "3"},
            fp=None,
        )

    monkeypatch.setenv("W2_PROVIDER_CALLS_DISABLED", "false")
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "lineups")
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "redacted-sentinel")
    monkeypatch.setattr(urllib.request, "urlopen", fail_transport)
    client = ApiFootballClient(
        allow_live=True,
        allowed_live_endpoints=frozenset({"lineups"}),
        request_ledger=FakeLedger(),
    )

    response = client.request_live("lineups", {"fixture": "1494214"})

    assert response.status_code == 503
    assert calls == 1
    assert len(records) == 1
    assert records[0]["status_code"] == 503
    assert records[0]["error"] == "PROVIDER_HTTP_503"
    assert "redacted-sentinel" not in repr(records)


@pytest.mark.parametrize(
    ("failure", "expected_error"),
    [
        (TimeoutError(), "PROVIDER_TIMEOUT"),
        (ConnectionResetError(), "PROVIDER_CONNECTION_ERROR"),
        (urllib.error.URLError("offline"), "PROVIDER_URL_ERROR"),
    ],
)
def test_api_football_transport_failure_records_one_sanitized_ledger_row(
    monkeypatch,
    failure: OSError,
    expected_error: str,
) -> None:
    calls = 0
    records: list[dict[str, object]] = []

    class FakeLedger:
        def record_request(self, **kwargs: object) -> None:
            records.append(kwargs)

    def fail_transport(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise failure

    monkeypatch.setenv("W2_PROVIDER_CALLS_DISABLED", "false")
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "lineups")
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "redacted-sentinel")
    monkeypatch.setattr(urllib.request, "urlopen", fail_transport)
    client = ApiFootballClient(
        allow_live=True,
        allowed_live_endpoints=frozenset({"lineups"}),
        request_ledger=FakeLedger(),
    )

    with pytest.raises(type(failure)):
        client.request_live("lineups", {"fixture": "1494214"})

    assert calls == 1
    assert len(records) == 1
    assert records[0]["status_code"] is None
    assert records[0]["error"] == expected_error
    assert records[0]["headers"] == {}
    assert records[0]["payload"] == {}
    assert "redacted-sentinel" not in repr(records)
