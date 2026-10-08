from __future__ import annotations

import json
import urllib.error
from unittest.mock import patch

from w2.providers.status import (
    fetch_provider_quota_live,
    parse_status_quota,
)

REAL_STATUS_PAYLOAD = {
    "get": "status",
    "response": {
        "account": {"firstname": "x", "lastname": "y", "email": "z"},
        "subscription": {
            "plan": "Pro",
            "end": "2026-10-16T16:10:05+00:00",
            "active": True,
        },
        "requests": {"current": 3128, "limit_day": 7500},
    },
}


class FakeUrlopenResponse:
    def __init__(self, status: int = 200, body: bytes = b"{}") -> None:
        self.status = status
        self._body = body

    def __enter__(self) -> "FakeUrlopenResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def test_parse_status_quota_real_shape() -> None:
    parsed = parse_status_quota(REAL_STATUS_PAYLOAD)
    assert parsed["current"] == 3128
    assert parsed["limit_day"] == 7500
    assert parsed["remaining"] == 4372
    assert parsed["plan"] == "Pro"
    assert parsed["plan_end"] == "2026-10-16T16:10:05+00:00"


def test_parse_status_quota_missing_requests_is_none() -> None:
    parsed = parse_status_quota({"response": {}})
    assert parsed["current"] is None
    assert parsed["limit_day"] is None
    assert parsed["remaining"] is None
    assert parsed["plan"] is None
    assert parsed["plan_end"] is None


def test_parse_status_quota_non_dict_response_is_none() -> None:
    parsed = parse_status_quota({"response": "not-a-dict"})
    assert parsed["current"] is None
    assert parsed["limit_day"] is None
    assert parsed["remaining"] is None


def test_fetch_live_missing_credential_is_degraded(monkeypatch) -> None:
    monkeypatch.delenv("W2_API_FOOTBALL_API_KEY", raising=False)
    result = fetch_provider_quota_live()
    assert result["degraded"] is True
    assert result["source"] == "cache"
    assert result["error"] == "PROVIDER_CREDENTIAL_MISSING"
    assert result["remaining"] is None


def test_fetch_live_success_returns_live_quota(monkeypatch) -> None:
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "test-key")
    body = json.dumps(REAL_STATUS_PAYLOAD).encode("utf-8")
    with patch(
        "urllib.request.urlopen",
        return_value=FakeUrlopenResponse(status=200, body=body),
    ):
        result = fetch_provider_quota_live()
    assert result["degraded"] is False
    assert result["source"] == "live"
    assert result["current"] == 3128
    assert result["limit_day"] == 7500
    assert result["remaining"] == 4372
    assert result["plan"] == "Pro"


def test_fetch_live_timeout_is_degraded(monkeypatch) -> None:
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "test-key")

    def _raise_timeout(*_args: object, **_kwargs: object) -> None:
        raise TimeoutError("timeout")

    with patch("urllib.request.urlopen", side_effect=_raise_timeout):
        result = fetch_provider_quota_live()
    assert result["degraded"] is True
    assert result["source"] == "cache"
    assert result["error"] == "PROVIDER_TIMEOUT"
    assert result["remaining"] is None


def test_fetch_live_http_error_is_degraded(monkeypatch) -> None:
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "test-key")
    http_error = urllib.error.HTTPError("http://x/status", 429, "Too Many", {}, None)
    with patch("urllib.request.urlopen", side_effect=http_error):
        result = fetch_provider_quota_live()
    assert result["degraded"] is True
    assert result["source"] == "cache"
    assert result["error"] == "PROVIDER_HTTP_429"
    assert result["remaining"] is None


def test_fetch_live_schema_drift_is_degraded(monkeypatch) -> None:
    monkeypatch.setenv("W2_API_FOOTBALL_API_KEY", "test-key")
    drift_payload = {"response": {"subscription": {"plan": "Pro"}}}
    body = json.dumps(drift_payload).encode("utf-8")
    with patch(
        "urllib.request.urlopen",
        return_value=FakeUrlopenResponse(status=200, body=body),
    ):
        result = fetch_provider_quota_live()
    assert result["degraded"] is True
    assert result["source"] == "cache"
    assert result["error"] == "PROVIDER_STATUS_SCHEMA_DRIFT"
    assert result["remaining"] is None
