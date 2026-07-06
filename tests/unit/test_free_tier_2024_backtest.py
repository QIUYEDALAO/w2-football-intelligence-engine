from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from w2.backtest.free_tier_2024 import (
    build_free_tier_2024_backtest_report,
    collect_provider_dataset,
)


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
