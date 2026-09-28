"""DA-XG-01 离线实现测试：核心方向 / 主客交换 / 中性先验 / clamp / 消融 /
rolling-origin 回放 / 覆盖报告 / 重复性哈希。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from w2.quant_research.da_xg_offline import (
    DaXgParameters,
    XgMatchRecord,
    coverage_report,
    predict,
    predict_baseline,
    rolling_origin_replay,
)


def _match(
    i: int, home: str, away: str, hxg: float, axg: float, season: str = "2026"
) -> XgMatchRecord:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return XgMatchRecord(
        fixture_id=f"f{i}",
        competition="l1",
        season=season,
        kickoff_utc=base + timedelta(days=i),
        captured_at=base + timedelta(days=i, hours=2),
        home_team=home,
        away_team=away,
        home_xg=hxg,
        away_xg=axg,
        home_goals=0,
        away_goals=0,
    )


def _strong_weak_matches() -> list[XgMatchRecord]:
    return [
        _match(0, "S", "X", 2.5, 0.5),
        _match(1, "Y", "S", 0.5, 2.5),
        _match(2, "S", "Z", 2.5, 0.5),
        _match(3, "Z", "S", 0.5, 2.5),
        _match(4, "S", "X", 2.5, 0.5),
        _match(5, "X", "W", 2.0, 0.3),
        _match(6, "W", "Y", 0.3, 2.0),
        _match(7, "X", "W", 2.0, 0.3),
        _match(8, "W", "Y", 0.3, 2.0),
        _match(9, "X", "W", 2.0, 0.3),
    ]


def _params() -> DaXgParameters:
    return DaXgParameters(league_baseline_min=5)


def _target_kickoff() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=20)


def test_strong_team_edges_weak_team() -> None:
    matches = _strong_weak_matches()
    pred = predict(
        fixture_id="t",
        home_team="S",
        away_team="W",
        kickoff_utc=_target_kickoff(),
        matches=matches,
        target_season="2026",
        competition="l1",
        params=_params(),
    )
    assert pred is not None
    assert pred.lambda_home > pred.lambda_away


def test_home_away_swap_flips_advantage() -> None:
    matches = _strong_weak_matches()
    away = predict(
        fixture_id="t",
        home_team="W",
        away_team="S",
        kickoff_utc=_target_kickoff(),
        matches=matches,
        target_season="2026",
        competition="l1",
        params=_params(),
    )
    assert away is not None
    assert away.lambda_away > away.lambda_home


def test_no_history_returns_none_not_fabricated() -> None:
    matches = _strong_weak_matches()
    pred = predict(
        fixture_id="t",
        home_team="NEW1",
        away_team="NEW2",
        kickoff_utc=_target_kickoff(),
        matches=matches,
        target_season="2026",
        competition="l1",
        params=_params(),
    )
    assert pred is None


def test_extreme_values_clamped() -> None:
    blast = [_match(i, "S", "X", 9.0, 0.1) for i in range(5)] + [
        _match(i + 5, "X", "W", 0.1, 9.0) for i in range(5)
    ]
    pred = predict(
        fixture_id="t",
        home_team="S",
        away_team="W",
        kickoff_utc=_target_kickoff(),
        matches=blast,
        target_season="2026",
        competition="l1",
        params=_params(),
    )
    assert pred is not None
    assert 1.35 <= pred.total_projection <= 4.40
    assert 0.15 <= pred.lambda_home <= 4.25
    assert 0.15 <= pred.lambda_away <= 4.25


def test_repeatable_artifact_hash() -> None:
    matches = _strong_weak_matches()
    first = predict(
        fixture_id="t", home_team="S", away_team="W", kickoff_utc=_target_kickoff(),
        matches=matches, target_season="2026", competition="l1", params=_params(),
    )
    second = predict(
        fixture_id="t", home_team="S", away_team="W", kickoff_utc=_target_kickoff(),
        matches=matches, target_season="2026", competition="l1", params=_params(),
    )
    assert first is not None and second is not None
    assert first.artifact_hash == second.artifact_hash


def test_baseline_and_challenger_same_batch_different_identity() -> None:
    matches = _strong_weak_matches()
    challenger = predict(
        fixture_id="t", home_team="S", away_team="W", kickoff_utc=_target_kickoff(),
        matches=matches, target_season="2026", competition="l1", params=_params(),
    )
    baseline = predict_baseline(
        fixture_id="t", home_team="S", away_team="W", kickoff_utc=_target_kickoff(),
        matches=matches, target_season="2026", competition="l1", params=_params(),
    )
    assert challenger is not None and baseline is not None
    assert challenger.model_identity != baseline.model_identity
    assert challenger.as_of_utc == baseline.as_of_utc


def test_ablations_do_not_crash_and_change_output() -> None:
    matches = _strong_weak_matches()
    base = predict(
        fixture_id="t", home_team="S", away_team="W", kickoff_utc=_target_kickoff(),
        matches=matches, target_season="2026", competition="l1", params=_params(),
    )
    assert base is not None
    ablated = predict(
        fixture_id="t", home_team="S", away_team="W", kickoff_utc=_target_kickoff(),
        matches=matches, target_season="2026", competition="l1",
        params=DaXgParameters(league_baseline_min=5, ablate_opponent_correction=True),
    )
    assert ablated is not None
    assert ablated.lambda_home != base.lambda_home


def test_rolling_origin_replay_and_coverage_report() -> None:
    matches = _strong_weak_matches()
    results = rolling_origin_replay(matches, params=_params())
    assert len(results) == len(matches)
    report = coverage_report(results)
    assert report["total"] == len(matches)
    assert report["coverage_rate"] >= 0.0
    assert "COVERAGE_INSUFFICIENT" in report["exclusion_reasons"]
