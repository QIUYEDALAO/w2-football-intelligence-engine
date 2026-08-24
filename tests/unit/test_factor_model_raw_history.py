from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from w2.factor_model.history import (
    API_FOOTBALL_TEAM_ID_NAMESPACE,
    HistoricalFixtureBatch,
    build_pit_history_manifest,
    materialize_factor_history_from_persisted_raw,
)

NOW = datetime(2026, 8, 21, 12, tzinfo=UTC)


class Repository:
    provider_calls = 0

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]:
        assert endpoint == "fixtures"
        return self.rows

    def request_live(self, *_args: Any, **_kwargs: Any) -> None:
        self.provider_calls += 1
        raise AssertionError("Provider must not be called")


def _fixture(
    fixture_id: int,
    *,
    kickoff: datetime,
    status: str,
    home_team_id: int | None = 10,
    away_team_id: int | None = 20,
    home_goals: int | None = None,
    away_goals: int | None = None,
) -> dict[str, Any]:
    return {
        "fixture": {
            "id": fixture_id,
            "date": kickoff.isoformat(),
            "status": {"short": status},
        },
        "league": {"id": 140, "season": 2025},
        "teams": {
            "home": {"id": home_team_id},
            "away": {"id": away_team_id},
        },
        "goals": {"home": home_goals, "away": away_goals},
    }


def _raw(index: str, captured_at: datetime, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "sha256": index * 64,
        "captured_at": captured_at,
        "payload": {"response": [item]},
    }


def _materialize(
    rows: list[dict[str, Any]], *, as_of: datetime = NOW
) -> HistoricalFixtureBatch:
    repository = Repository(rows)
    batch = materialize_factor_history_from_persisted_raw(
        repository,
        kickoff_from=NOW - timedelta(days=10),
        kickoff_to=NOW + timedelta(days=1),
        as_of=as_of,
    )
    assert repository.provider_calls == 0
    return batch


def test_latest_asof_observation_replaces_early_ns_without_identity_conflict() -> None:
    kickoff = NOW - timedelta(days=3)
    finished_at = kickoff + timedelta(hours=40)
    batch = _materialize(
        [
            _raw("a", kickoff - timedelta(days=1), _fixture(1, kickoff=kickoff, status="NS")),
            _raw(
                "b",
                finished_at,
                _fixture(
                    1,
                    kickoff=kickoff,
                    status="FT",
                    home_goals=2,
                    away_goals=1,
                ),
            ),
        ]
    )

    assert len(batch.history_rows) == 2
    assert {row["raw_payload_sha256"] for row in batch.history_rows} == {"b" * 64}
    assert {row["raw_captured_at"] for row in batch.history_rows} == {finished_at}
    assert {row["team_identity_namespace"] for row in batch.history_rows} == {
        API_FOOTBALL_TEAM_ID_NAMESPACE
    }
    assert {row["team_id"] for row in batch.history_rows} == {"10", "20"}
    assert all("team_w2_id" not in row for row in batch.history_rows)
    totals = batch.coverage_report["totals"]
    assert totals["eligible_finished_fixture_count"] == 1
    assert totals["late_result_fixture_count"] == 1
    assert totals.get("conflict_fixture_count", 0) == 0
    assert batch.coverage_report["provider_calls"] == 0
    assert batch.coverage_report["database_writes"] == 0
    assert len(batch.corpus_sha256) == 64

    manifest = build_pit_history_manifest(
        list(batch.history_rows),
        target_fixture_id="api_football:target",
        target_kickoff=NOW,
        feature_as_of=NOW,
        team_identity_namespace=API_FOOTBALL_TEAM_ID_NAMESPACE,
    )
    source = manifest["source_fixtures"][0]
    assert source["provider_league_id"] == "140"
    assert source["home_team_id"] == "10"
    assert source["away_team_id"] == "20"
    assert source["source_raw_payload_sha256"] == ["b" * 64]


def test_raw_capture_at_feature_asof_is_not_visible() -> None:
    kickoff = NOW - timedelta(days=2)
    batch = _materialize(
        [
            _raw("a", NOW - timedelta(hours=2), _fixture(1, kickoff=kickoff, status="NS")),
            _raw(
                "b",
                NOW,
                _fixture(
                    1,
                    kickoff=kickoff,
                    status="FT",
                    home_goals=1,
                    away_goals=0,
                ),
            ),
        ]
    )

    assert batch.history_rows == ()
    assert batch.coverage_report["totals"]["unfinished_fixture_count"] == 1
    assert batch.coverage_report["totals"].get("conflict_fixture_count", 0) == 0


def test_coverage_reports_missing_identity_unfinished_and_latest_conflict() -> None:
    kickoff = NOW - timedelta(days=2)
    captured_at = NOW - timedelta(hours=1)
    batch = _materialize(
        [
            _raw("a", captured_at, _fixture(1, kickoff=kickoff, status="NS")),
            _raw(
                "b",
                captured_at,
                _fixture(
                    2,
                    kickoff=kickoff,
                    status="FT",
                    away_team_id=None,
                    home_goals=1,
                    away_goals=0,
                ),
            ),
            _raw("c", captured_at, _fixture(3, kickoff=kickoff, status="NS")),
            _raw(
                "d",
                captured_at,
                _fixture(
                    3,
                    kickoff=kickoff,
                    status="FT",
                    home_goals=2,
                    away_goals=2,
                ),
            ),
        ]
    )

    totals = batch.coverage_report["totals"]
    assert totals["identity_missing_fixture_count"] == 1
    assert totals["unfinished_fixture_count"] == 1
    assert totals["conflict_fixture_count"] == 1
    scope = batch.coverage_report["by_league_season"]
    assert [(row["provider_league_id"], row["season"]) for row in scope] == [
        ("140", "2025")
    ]
    assert scope[0]["identity_missing_fixture_count"] == 1
    assert scope[0]["unfinished_fixture_count"] == 1
    assert scope[0]["conflict_fixture_count"] == 1
