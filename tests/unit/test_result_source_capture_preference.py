"""赛果物化 source 选择：比分一致时优先选「有 matchday capture 映射」的 raw。"""
from __future__ import annotations

from datetime import UTC, datetime

from w2.tracking.outcome_ledger_repository import _authoritative_result

FUTURE_REFRESH_HASH = "6426128e4c76849bb84911be4b2817c28f59a163a7be39a7f7e2f3f52545c48c"
MATCHDAY_HASH = "e35ac83db304dd1c4ce639f78e815f804a2b2bdccba51f665f6f9a370762c1b6"


def _item(status: str, home: int, away: int) -> dict:
    return {
        "fixture": {"status": {"short": status}},
        "score": {"fulltime": {"home": home, "away": away}},
    }


def test_authoritative_result_prefers_captured_source() -> None:
    """单变量攻击：两条 FT 比分一致（1:1），无 preferred 取最早；有 preferred 取有 capture 者。

    复现生产 1493157：6426128e（future_refresh 采集 21:46、无 matchday capture）比
    e35ac83d（matchday 采集 21:49、有 capture）更早。旧逻辑取 6426128e → source_capture_id
    解析不到 → V3_RESULT_CAPTURE_MISSING。修复后优先取 e35ac83d。
    """
    early = datetime(2026, 10, 5, 21, 46, 1, tzinfo=UTC)
    late = datetime(2026, 10, 5, 21, 49, 3, tzinfo=UTC)
    candidates = [
        (early, FUTURE_REFRESH_HASH, _item("FT", 1, 1)),
        (late, MATCHDAY_HASH, _item("FT", 1, 1)),
    ]
    # 空操作控制：无 preferred → 仍按 captured_at 取最早（旧行为不变）。
    outcome = _authoritative_result("fx", candidates)
    assert outcome["source_payload_sha256"] == FUTURE_REFRESH_HASH
    assert (outcome["home_goals"], outcome["away_goals"]) == (1, 1)
    # 单变量攻击：preferred 含 matchday capture 的 hash → 优先选它。
    outcome = _authoritative_result(
        "fx", candidates, preferred_source_hashes=frozenset({MATCHDAY_HASH})
    )
    assert outcome["source_payload_sha256"] == MATCHDAY_HASH
    assert (outcome["home_goals"], outcome["away_goals"]) == (1, 1)


def test_authoritative_result_keeps_conflict_detection() -> None:
    """反向控制：比分不一致仍 RESULT_SOURCE_CONFLICT，preferred 不掩盖冲突。"""
    candidates = [
        (datetime(2026, 10, 5, 21, 46, tzinfo=UTC), FUTURE_REFRESH_HASH, _item("FT", 1, 1)),
        (datetime(2026, 10, 5, 21, 49, tzinfo=UTC), MATCHDAY_HASH, _item("FT", 2, 1)),
    ]
    outcome = _authoritative_result(
        "fx", candidates, preferred_source_hashes=frozenset({MATCHDAY_HASH})
    )
    assert outcome["status"] == "RESULT_SOURCE_CONFLICT"
