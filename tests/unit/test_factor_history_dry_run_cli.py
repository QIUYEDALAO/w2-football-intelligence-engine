from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from scripts.materialize_factor_history_dry_run import build_report, write_artifacts

NOW = datetime(2026, 8, 21, 12, tzinfo=UTC)


def _raw(
    fixture_id: int,
    *,
    season: int,
    status: str,
    goals: tuple[int | None, int | None],
    captured_at: datetime,
) -> dict[str, Any]:
    return {
        "sha256": f"{fixture_id:064x}",
        "captured_at": captured_at.isoformat(),
        "payload": {
            "response": [
                {
                    "fixture": {
                        "id": fixture_id,
                        "date": (NOW - timedelta(days=2)).isoformat(),
                        "status": {"short": status},
                    },
                    "league": {"id": 140, "season": season},
                    "teams": {"home": {"id": 10}, "away": {"id": 20}},
                    "goals": {"home": goals[0], "away": goals[1]},
                }
            ]
        },
    }


def test_gate1_dry_run_builds_exact_13_by_3_report_without_side_effects(tmp_path) -> None:
    corpus, report = build_report(
        [
            _raw(
                1,
                season=2025,
                status="FT",
                goals=(2, 1),
                captured_at=NOW - timedelta(days=1),
            ),
            _raw(
                2,
                season=2025,
                status="NS",
                goals=(None, None),
                captured_at=NOW - timedelta(days=1),
            ),
        ],
        kickoff_from=datetime(2024, 1, 1, tzinfo=UTC),
        kickoff_to=datetime(2027, 1, 1, tzinfo=UTC),
        as_of=NOW,
        seasons=("2024", "2025", "2026"),
    )

    assert report["scope"]["competition_count"] == 13
    assert report["scope"]["league_season_count"] == 39
    assert len(report["by_league_season"]) == 39
    assert report["contracts"] == {
        "selection_policy": "LATEST_RAW_CAPTURE_STRICTLY_BEFORE_FEATURE_AS_OF",
        "team_identity_namespace": "api_football.provider_team_id.v1",
        "provider_calls": 0,
        "database_writes": 0,
        "split_frozen": False,
        "training_executed": False,
        "deployment_executed": False,
    }
    la_liga = next(
        row
        for row in report["by_league_season"]
        if row["competition_id"] == "la_liga" and row["season"] == "2025"
    )
    assert la_liga["eligible_finished_fixture_count"] == 1
    assert la_liga["unfinished_fixture_count"] == 1
    assert la_liga["point_in_time_exclusion_reasons"] == {
        "IDENTITY_MISSING_AT_LATEST_VISIBLE_CAPTURE": 0,
        "KICKOFF_OUTSIDE_HALF_OPEN_HISTORY_WINDOW": 0,
        "LATEST_VISIBLE_CAPTURE_CONFLICT": 0,
        "LATEST_VISIBLE_STATUS_NOT_FINISHED": 1,
        "LATEST_VISIBLE_TERMINAL_RESULT_MISSING": 0,
    }
    assert report["point_in_time_exclusion_reasons"][
        "LATEST_VISIBLE_STATUS_NOT_FINISHED"
    ] == 1
    assert corpus["history_rows"][0]["team_identity_namespace"] == (
        "api_football.provider_team_id.v1"
    )

    write_artifacts(tmp_path, corpus, report)
    assert {path.name for path in tmp_path.iterdir()} == {
        "factor_history_corpus.json",
        "factor_history_coverage.json",
        "factor_history_coverage.md",
    }
