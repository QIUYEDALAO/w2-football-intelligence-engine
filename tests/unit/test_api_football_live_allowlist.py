from __future__ import annotations

import json
import urllib.request

import pytest

from w2.providers.api_football import ApiFootballClient, LiveNetworkDisabledError


def test_api_football_live_endpoint_allowlist_blocks_unapproved_endpoint() -> None:
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

    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "test-key")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = ApiFootballClient(
        allow_live=True,
        allowed_live_endpoints=frozenset({"statistics"}),
    )

    response = client.request_live("statistics", {"fixture": "1489404"})

    assert response.status_code == 200
    assert captured["url"].endswith("/fixtures/statistics?fixture=1489404")
