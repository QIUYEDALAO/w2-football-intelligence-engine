from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from w2.backtest.free_tier_2024 import (
    UNDERSTAT_XG_SOURCE,
    build_free_tier_2024_backtest_report,
    build_true_xg_delta_report,
    build_understat_model_iteration_report,
    build_understat_model_robustness_report,
    collect_provider_dataset,
    collect_understat_xg_dataset,
    load_fixture_statistics,
    load_historical_fixtures,
    load_understat_xg_statistics,
)
from w2.competitions.registry import CompetitionRegistry


def test_free_tier_backtest_uses_only_prematch_rolling_inputs(tmp_path: Path) -> None:
    _write_fixture_raw(
        tmp_path / "fixtures_premier_league_39_2024.json",
        league_id="39",
        season="2024",
        rows=[
            _fixture("fixture-1", "2024-01-01T12:00:00+00:00", "A", "B", 1, 0),
            _fixture("fixture-2", "2024-01-08T12:00:00+00:00", "B", "A", 2, 2),
            _fixture("fixture-3", "2024-01-15T12:00:00+00:00", "A", "B", 0, 3),
            _fixture("fixture-4", "2024-01-22T12:00:00+00:00", "B", "A", 1, 1),
        ],
    )

    report = build_free_tier_2024_backtest_report(
        raw_dirs=(tmp_path,),
        competitions=("premier_league",),
        generated_at=None,
    )

    assert report["provider_calls"] == 0
    assert report["db_writes"] == 0
    assert report["overall"]["sample_count"] == 4
    samples = report["outcome_tracked_samples"]
    assert samples[0]["outcome_tracked"] is True
    assert report["model"]["forbidden_inputs"] == [
        "odds",
        "market_line",
        "closing_price",
        "result_as_feature",
    ]


def test_backtest_reports_missing_inputs_and_competition_slices(tmp_path: Path) -> None:
    _write_fixture_raw(
        tmp_path / "fixtures_premier_league_39_2024.json",
        league_id="39",
        season="2024",
        rows=[_fixture("fixture-1", "2024-01-01T12:00:00+00:00", "A", "B", 1, 0)],
    )

    report = build_free_tier_2024_backtest_report(
        raw_dirs=(tmp_path,),
        competitions=("premier_league", "la_liga"),
    )

    assert report["scope"]["covered_competitions"] == ["premier_league"]
    assert report["scope"]["missing_competitions"] == ["la_liga"]
    assert report["calibration_status"]["status"] == "BLOCKED"
    assert "MISSING_2024_FIXTURE_RAW" in report["calibration_status"]["blockers"]
    assert "SQUAD_VALUE_MISSING" in report["calibration_status"]["warnings"]


def test_provider_collection_reuses_existing_fixture_cache_and_caps_calls(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "raw" / "fixtures_premier_league_39_2024.json"
    _write_fixture_raw(
        existing,
        league_id="39",
        season="2024",
        rows=[_fixture("fixture-1", "2024-01-01T12:00:00+00:00", "A", "B", 1, 0)],
    )
    calls: list[tuple[str, dict[str, str]]] = []

    def requester(
        endpoint: str,
        params: dict[str, str],
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        calls.append((endpoint, params))
        return (
            200,
            {"x-ratelimit-requests-remaining": "80"},
            {"response": [_fixture("fixture-2", "2024-01-02T12:00:00+00:00", "C", "D", 2, 0)]},
        )

    result = collect_provider_dataset(
        out_dir=tmp_path,
        competitions=("premier_league", "la_liga"),
        reuse_raw_dirs=(),
        daily_hard_cap=1,
        request_interval_seconds=0,
        requester=requester,
    )

    assert result.provider_calls == 1
    assert len(calls) == 1
    assert calls[0] == ("fixtures", {"league": "140", "season": "2024", "status": "FT"})
    assert result.stopped_reason is None
    assert result.skipped_existing == (existing.as_posix(),)


def test_provider_collection_can_fetch_limited_statistics_without_real_sleep(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def requester(
        endpoint: str,
        params: dict[str, str],
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        calls.append(endpoint)
        if endpoint == "fixtures":
            return (
                200,
                {"x-ratelimit-requests-remaining": "80"},
                {"response": [_fixture("fixture-1", "2024-01-01T12:00:00+00:00", "A", "B", 1, 0)]},
            )
        return (
            200,
            {"x-ratelimit-requests-remaining": "79"},
            {
                "response": [
                    {
                        "team": {"name": "A"},
                        "statistics": [{"type": "expected_goals", "value": "1.2"}],
                    }
                ]
            },
        )

    result = collect_provider_dataset(
        out_dir=tmp_path,
        competitions=("premier_league",),
        reuse_raw_dirs=(),
        daily_hard_cap=2,
        max_statistics_calls=1,
        request_interval_seconds=0,
        requester=requester,
    )

    assert result.provider_calls == 2
    assert calls == ["fixtures", "statistics"]
    assert (tmp_path / "raw" / "statistics_premier_league_fixture-1.json").exists()


def test_true_xg_comparison_excludes_target_fixture_statistics(tmp_path: Path) -> None:
    rows = [
        _fixture(f"fixture-{index}", f"2024-01-{index:02d}T12:00:00+00:00", "A", "B", 1, 0)
        for index in range(1, 7)
    ]
    _write_fixture_raw(
        tmp_path / "fixtures_premier_league_39_2024.json",
        league_id="39",
        season="2024",
        rows=rows,
    )
    for index in range(1, 6):
        _write_statistics_raw(
            tmp_path / f"statistics_fixture-{index}.json",
            fixture_id=f"fixture-{index}",
            home="A",
            away="B",
            home_xg=1.0,
            away_xg=0.5,
        )
    _write_statistics_raw(
        tmp_path / "statistics_fixture-6.json",
        fixture_id="fixture-6",
        home="A",
        away="B",
        home_xg=9.0,
        away_xg=8.0,
    )

    fixtures = load_historical_fixtures(
        raw_dirs=(tmp_path,),
        entries=CompetitionRegistry().entries(),
        season="2024",
        competitions=("premier_league",),
    )
    report = build_true_xg_delta_report(
        fixtures=fixtures,
        statistics_by_fixture=load_fixture_statistics((tmp_path,)),
        min_history=5,
    )

    assert report["sample_count"] == 1
    row = report["sample_rows"][0]
    assert row["fixture_id"] == "fixture-6"
    assert row["prior_home_xg_for"] == 1.0
    assert row["prior_away_xg_for"] == 0.5
    assert row["target_fixture_xg_excluded_from_features"] is True


def test_understat_xg_source_maps_names_and_excludes_target_fixture_xg(tmp_path: Path) -> None:
    rows = [
        _fixture(
            f"fixture-{index}",
            f"2024-01-{index:02d}T12:00:00+00:00",
            "Newcastle",
            "Wolves",
            1,
            0,
        )
        for index in range(1, 7)
    ]
    _write_fixture_raw(
        tmp_path / "fixtures_premier_league_39_2024.json",
        league_id="39",
        season="2024",
        rows=rows,
    )
    _write_understat_cache(
        tmp_path / "understat_epl_2024.json",
        [
            _understat_match(
                f"fixture-{index}",
                f"2024-01-{index:02d} 12:00:00",
                "Newcastle United",
                "Wolverhampton Wanderers",
                1.0,
                0.5,
            )
            for index in range(1, 6)
        ]
        + [
            _understat_match(
                "fixture-6",
                "2024-01-06 13:00:00",
                "Newcastle United",
                "Wolverhampton Wanderers",
                9.0,
                8.0,
            )
        ],
    )
    fixtures = load_historical_fixtures(
        raw_dirs=(tmp_path,),
        entries=CompetitionRegistry().entries(),
        season="2024",
        competitions=("premier_league",),
    )

    understat_stats = load_understat_xg_statistics(
        raw_dirs=(tmp_path,),
        fixtures=fixtures,
        season="2024",
    )
    report = build_true_xg_delta_report(
        fixtures=fixtures,
        statistics_by_fixture=understat_stats,
        xg_source=UNDERSTAT_XG_SOURCE,
        min_history=5,
    )

    assert understat_stats["fixture-6"] == {"Newcastle": 9.0, "Wolves": 8.0}
    assert report["xg_source"] == UNDERSTAT_XG_SOURCE
    assert report["sample_count"] == 1
    row = report["sample_rows"][0]
    assert row["fixture_id"] == "fixture-6"
    assert row["prior_home_xg_for"] == 1.0
    assert row["prior_away_xg_for"] == 0.5
    assert row["target_fixture_xg_excluded_from_features"] is True


def test_understat_collection_writes_cache_and_reuses_existing_file(tmp_path: Path) -> None:
    requests: list[tuple[str, str]] = []

    def requester(league_code: str, season: str) -> dict[str, Any]:
        requests.append((league_code, season))
        return {"dates": [_understat_match("fixture-1", "2024-01-01 12:00:00", "A", "B", 1.1, 0.9)]}

    first = collect_understat_xg_dataset(out_dir=tmp_path, requester=requester)
    second = collect_understat_xg_dataset(out_dir=tmp_path, requester=requester)

    assert first.provider_calls == 0
    assert first.understat_requests == 1
    assert first.fixture_count == 1
    assert second.provider_calls == 0
    assert second.understat_requests == 0
    assert second.skipped_existing is True
    assert requests == [("EPL", "2024")]


def test_understat_model_iteration_report_is_offline_and_has_validation(tmp_path: Path) -> None:
    start = datetime(2024, 1, 1, 12, tzinfo=UTC)
    fixture_rows = []
    understat_rows = []
    for index in range(260):
        kickoff = start + timedelta(days=index)
        home = "A" if index % 2 == 0 else "B"
        away = "B" if index % 2 == 0 else "A"
        home_goals = 2 if index % 3 == 0 else 1
        away_goals = 1 if index % 5 == 0 else 0
        fixture_rows.append(
            _fixture(
                f"fixture-{index}",
                kickoff.isoformat(),
                home,
                away,
                home_goals,
                away_goals,
            )
        )
        understat_rows.append(
            _understat_match(
                f"understat-{index}",
                kickoff.strftime("%Y-%m-%d %H:%M:%S"),
                home,
                away,
                1.4 if home_goals > away_goals else 0.8,
                0.8 if home_goals > away_goals else 1.2,
            )
        )
    _write_fixture_raw(
        tmp_path / "fixtures_premier_league_39_2024.json",
        league_id="39",
        season="2024",
        rows=fixture_rows,
    )
    _write_understat_cache(tmp_path / "understat_epl_2024.json", understat_rows)

    report = build_understat_model_iteration_report(
        raw_dirs=(tmp_path,),
        competitions=("premier_league",),
        min_history=5,
    )

    assert report["eligible_sample_count"] >= 200
    assert report["model"]["online_lambda_fit_enabled"] is False
    assert report["safety"]["api_football_provider_calls"] == 0
    assert report["validation"]["baseline_prior"]["metrics"] is not None
    assert report["validation"]["fitted_calibrated"]["metrics"] is not None


def test_understat_model_robustness_report_has_gap_cross_season_and_folds(
    tmp_path: Path,
) -> None:
    for season, year in (("2023", 2023), ("2024", 2024)):
        rows = []
        start = datetime(year, 1, 1, 12, tzinfo=UTC)
        for index in range(240):
            kickoff = start + timedelta(days=index)
            home = "A" if index % 2 == 0 else "B"
            away = "B" if index % 2 == 0 else "A"
            rows.append(
                _understat_match(
                    f"{season}-{index}",
                    kickoff.strftime("%Y-%m-%d %H:%M:%S"),
                    home,
                    away,
                    1.5 if index % 3 == 0 else 0.9,
                    0.8 if index % 3 == 0 else 1.2,
                    home_goals=2 if index % 3 == 0 else 1,
                    away_goals=0 if index % 3 == 0 else 1,
                )
            )
        _write_understat_cache(tmp_path / f"understat_epl_{season}.json", rows, season=season)

    report = build_understat_model_robustness_report(
        raw_dirs=(tmp_path,),
        seasons=("2023", "2024"),
        competitions=("premier_league",),
        min_history=5,
    )

    assert report["safety"]["api_football_provider_calls"] == 0
    assert report["train_validation_gap"]["train"]["fitted_calibrated"]["metrics"] is not None
    assert len(report["cross_season"]) == 2
    assert report["rolling_origin"]["summary"]["fold_count"] >= 1
    assert report["interpretation"]["status"] in {
        "ROBUST_IMPROVEMENT",
        "PROMISING_BUT_CROSS_SEASON_MIXED",
        "NOT_ROBUST_ENOUGH",
    }


def test_provider_collection_skips_existing_statistics_cache(tmp_path: Path) -> None:
    _write_fixture_raw(
        tmp_path / "raw" / "fixtures_premier_league_39_2024.json",
        league_id="39",
        season="2024",
        rows=[_fixture("fixture-1", "2024-01-01T12:00:00+00:00", "A", "B", 1, 0)],
    )
    _write_statistics_raw(
        tmp_path / "raw" / "statistics_premier_league_fixture-1.json",
        fixture_id="fixture-1",
        home="A",
        away="B",
        home_xg=1.0,
        away_xg=0.5,
    )
    calls: list[str] = []

    def requester(
        endpoint: str,
        params: dict[str, str],
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        calls.append(endpoint)
        return 200, {"x-ratelimit-requests-remaining": "80"}, {"response": []}

    result = collect_provider_dataset(
        out_dir=tmp_path,
        competitions=("premier_league",),
        reuse_raw_dirs=(),
        daily_hard_cap=5,
        max_statistics_calls=1,
        request_interval_seconds=0,
        requester=requester,
    )

    assert result.provider_calls == 0
    assert calls == []
    assert result.skipped_existing == (
        (tmp_path / "raw" / "fixtures_premier_league_39_2024.json").as_posix(),
        (tmp_path / "raw" / "statistics_premier_league_fixture-1.json").as_posix(),
    )


def _write_fixture_raw(
    path: Path,
    *,
    league_id: str,
    season: str,
    rows: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "endpoint": "fixtures",
                "params": {"league": league_id, "season": season},
                "payload": {"response": rows},
            }
        ),
        encoding="utf-8",
    )


def _fixture(
    fixture_id: str,
    kickoff: str,
    home: str,
    away: str,
    home_goals: int,
    away_goals: int,
) -> dict[str, Any]:
    return {
        "fixture": {
            "id": fixture_id,
            "date": kickoff,
            "status": {"short": "FT"},
            "venue": {"id": 1},
        },
        "teams": {
            "home": {"name": home},
            "away": {"name": away},
        },
        "goals": {"home": home_goals, "away": away_goals},
    }


def _write_statistics_raw(
    path: Path,
    *,
    fixture_id: str,
    home: str,
    away: str,
    home_xg: float,
    away_xg: float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "endpoint": "statistics",
                "params": {"fixture": fixture_id},
                "payload": {
                    "response": [
                        {
                            "team": {"name": home},
                            "statistics": [{"type": "expected_goals", "value": str(home_xg)}],
                        },
                        {
                            "team": {"name": away},
                            "statistics": [{"type": "expected_goals", "value": str(away_xg)}],
                        },
                    ]
                },
            }
        ),
        encoding="utf-8",
    )


def _write_understat_cache(
    path: Path,
    rows: list[dict[str, Any]],
    *,
    season: str = "2024",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "source": UNDERSTAT_XG_SOURCE,
                "endpoint": "understat_league_data",
                "league_code": "EPL",
                "season": season,
                "payload": {"dates": rows},
            }
        ),
        encoding="utf-8",
    )


def _understat_match(
    match_id: str,
    kickoff: str,
    home: str,
    away: str,
    home_xg: float,
    away_xg: float,
    home_goals: int = 1,
    away_goals: int = 0,
) -> dict[str, Any]:
    return {
        "id": match_id,
        "isResult": True,
        "datetime": kickoff,
        "h": {"title": home},
        "a": {"title": away},
        "goals": {"h": str(home_goals), "a": str(away_goals)},
        "xG": {"h": str(home_xg), "a": str(away_xg)},
    }
