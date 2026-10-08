from __future__ import annotations

from unittest.mock import patch

import w2.dashboard.system_health as sh
from w2.dashboard.system_health import _collection_quota


class _FakeRow:
    def __init__(self, payload: dict) -> None:
        self.payload = payload


class _FakeSession:
    def __init__(self, row_payload: dict | None) -> None:
        self._row = _FakeRow(row_payload) if row_payload is not None else None

    def scalar(self, _stmt):  # noqa: ANN001, ANN201
        return self._row


def test_collection_quota_live_uses_real_remaining() -> None:
    """实时 /status 可读 → remaining = limit_day - current，绿灯，不 QUOTA_UNKNOWN。"""
    live = {
        "degraded": False,
        "current": 3128,
        "limit_day": 7500,
        "remaining": 4372,
        "plan": "Pro",
    }
    with patch("w2.dashboard.system_health._fetch_quota_live_cached", return_value=live):
        quota = _collection_quota(_FakeSession({}))
    assert quota["remaining_quota"] == 4372
    assert quota["ok"] is True
    assert quota["status"] == "READY"
    assert quota["source"] == "live"
    assert quota["current"] == 3128
    assert quota["limit_day"] == 7500


def test_collection_quota_degraded_falls_back_to_cache() -> None:
    """实时查不到 → 降级读缓存 remaining_quota + status 标记 DEGRADED。"""
    degraded = {"degraded": True, "error": "PROVIDER_TIMEOUT", "remaining": None}
    cache = {"remaining_quota": 300}
    with patch("w2.dashboard.system_health._fetch_quota_live_cached", return_value=degraded):
        quota = _collection_quota(_FakeSession(cache))
    assert quota["remaining_quota"] == 300
    assert quota["ok"] is False  # 300 <= 500 保留桶
    assert quota["status"] == "DEGRADED"
    assert quota["source"] == "cache"


def test_collection_quota_degraded_no_cache_is_unknown() -> None:
    """实时查不到且缓存也无 → remaining_quota=None（QUOTA_UNKNOWN），不造假。"""
    degraded = {"degraded": True, "error": "PROVIDER_TIMEOUT", "remaining": None}
    with patch("w2.dashboard.system_health._fetch_quota_live_cached", return_value=degraded):
        quota = _collection_quota(_FakeSession(None))
    assert quota["remaining_quota"] is None
    assert quota["ok"] is False
    assert quota["source"] == "cache"


def test_fetch_quota_live_cached_hits_ttl(monkeypatch) -> None:
    """连续两次调用，第二次命中缓存（60s TTL 内不重复外呼 /status）。"""
    sh._status_quota_cache.clear()
    calls: list[int] = []

    def fake_fetch() -> dict:
        calls.append(1)
        return {
            "degraded": False,
            "current": 3128,
            "limit_day": 7500,
            "remaining": 4372,
        }

    monkeypatch.setattr(sh, "fetch_provider_quota_live", fake_fetch)
    first = sh._fetch_quota_live_cached()
    second = sh._fetch_quota_live_cached()
    assert first["remaining"] == 4372
    assert second["remaining"] == 4372
    assert len(calls) == 1  # 第二次命中缓存，不重复外呼
