from __future__ import annotations

import json
import urllib.request

import pytest

from w2.providers.api_football import ApiFootballClient, LiveNetworkDisabledError
from w2.providers.control import ProviderCallsDisabledError


def test_api_football_live_endpoint_allowlist_blocks_unapproved_endpoint(monkeypatch) -> None:
    monkeypatch.delenv("W2_PROVIDER_CALLS_DISABLED", raising=False)
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

    monkeypatch.delenv("W2_PROVIDER_CALLS_DISABLED", raising=False)
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

    monkeypatch.delenv("W2_PROVIDER_CALLS_DISABLED", raising=False)
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
