"""F9 回测口径快照语义自测：captured_before_cutoff 参数。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from w2.features.xg_materialization import TeamXgMatch, materialize_rolling_xg


def _match(fixture_id: str, *, kickoff: datetime, captured: datetime) -> TeamXgMatch:
    return TeamXgMatch(
        fixture_id=fixture_id,
        team_id="T",
        opponent_team_id="OPP",
        kickoff_at=kickoff,
        captured_at=captured,
        xg_for=1.0,
        xg_against=0.5,
        goals_for=1,
        goals_against=0,
        raw_payload_sha256="h",
        source_system="test",
    )


def test_forward_pit_excludes_late_captured() -> None:
    cutoff = datetime(2026, 6, 1, tzinfo=UTC)
    matches = [
        _match("f1", kickoff=cutoff - timedelta(days=30), captured=cutoff + timedelta(days=1)),
        _match("f2", kickoff=cutoff - timedelta(days=20), captured=cutoff + timedelta(days=2)),
        _match("f3", kickoff=cutoff - timedelta(days=10), captured=cutoff + timedelta(days=3)),
    ]
    # 默认 PIT 口径：captured_at >= cutoff 被排除 → 不足 3 场 → None
    assert (
        materialize_rolling_xg(
            team_id="T",
            as_of_fixture_id="fx",
            as_of_time=cutoff,
            matches=matches,
            window=5,
            min_matches=3,
        )
        is None
    )


def test_backtest_lookback_uses_kickoff_only() -> None:
    cutoff = datetime(2026, 6, 1, tzinfo=UTC)
    matches = [
        _match("f1", kickoff=cutoff - timedelta(days=30), captured=cutoff + timedelta(days=1)),
        _match("f2", kickoff=cutoff - timedelta(days=20), captured=cutoff + timedelta(days=2)),
        _match("f3", kickoff=cutoff - timedelta(days=10), captured=cutoff + timedelta(days=3)),
    ]
    # 回测口径：captured_at 视为比赛时点，只 kickoff < cutoff 门控 → 3 场入选
    snap = materialize_rolling_xg(
        team_id="T",
        as_of_fixture_id="fx",
        as_of_time=cutoff,
        matches=matches,
        window=5,
        min_matches=3,
        captured_before_cutoff=False,
    )
    assert snap is not None
    assert snap.match_count == 3
    assert snap.rolling_xg_for == 1.0
    assert snap.rolling_xg_against == 0.5
    # available_at 只取 kickoff 最大值，不含 late captured_at
    assert snap.as_of_time == cutoff - timedelta(days=10)


def test_backtest_still_respects_kickoff_cutoff() -> None:
    cutoff = datetime(2026, 6, 1, tzinfo=UTC)
    matches = [
        _match("f1", kickoff=cutoff - timedelta(days=5), captured=cutoff - timedelta(days=6)),
        # 目标场之后的比赛（kickoff >= cutoff）绝不入选
        _match("f2", kickoff=cutoff + timedelta(days=1), captured=cutoff - timedelta(days=1)),
    ]
    # 只有 f1 在 cutoff 之前，不足 min_matches=3 → None
    assert (
        materialize_rolling_xg(
            team_id="T",
            as_of_fixture_id="fx",
            as_of_time=cutoff,
            matches=matches,
            window=5,
            min_matches=3,
            captured_before_cutoff=False,
        )
        is None
    )
