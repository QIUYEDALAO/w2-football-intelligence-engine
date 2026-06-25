from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from w2.features.xg_materialization import (
    materialize_rolling_xg,
    parse_team_xg_matches,
)
from w2.ingestion.xg_backfill import XgBackfillConfig, XgHistoryBackfillService
from w2.providers.api_football import LiveApiFootballResponse

NOW = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)


def finished_fixture(
    fixture_id: str,
    kickoff: datetime,
    home: str = "10",
    away: str = "20",
) -> dict[str, Any]:
    return {
        "fixture": {
            "id": fixture_id,
            "date": kickoff.isoformat().replace("+00:00", "Z"),
            "status": {"short": "FT"},
        },
        "teams": {"home": {"id": int(home)}, "away": {"id": int(away)}},
        "goals": {"home": 2, "away": 1},
    }


def statistics(
    home: str = "10",
    away: str = "20",
    home_xg: str = "1.7",
    away_xg: str = "0.8",
) -> dict[str, Any]:
    return {
        "response": [
            {
                "team": {"id": int(home)},
                "statistics": [{"type": "expected_goals", "value": home_xg}],
            },
            {
                "team": {"id": int(away)},
                "statistics": [{"type": "expected_goals", "value": away_xg}],
            },
        ]
    }


def test_parse_team_xg_matches_requires_finished_fixture_and_expected_goals() -> None:
    rows = parse_team_xg_matches(
        fixture_payload=finished_fixture("h1", NOW - timedelta(days=1)),
        statistics_payload=statistics(),
        captured_at=NOW,
        raw_payload_sha256="a" * 64,
    )

    assert [row.team_id for row in rows] == ["10", "20"]
    assert rows[0].xg_for == 1.7
    assert rows[0].xg_against == 0.8
    assert rows[0].candidate is False
    assert rows[0].formal_recommendation is False


def test_rolling_xg_materialization_is_strictly_as_of() -> None:
    rows = []
    for index in range(4):
        rows.extend(
            parse_team_xg_matches(
                fixture_payload=finished_fixture(f"h{index}", NOW - timedelta(days=5 - index)),
                statistics_payload=statistics(home_xg=str(1.0 + index), away_xg="0.5"),
                captured_at=NOW,
                raw_payload_sha256=f"{index}" * 64,
            )
        )
    future_rows = parse_team_xg_matches(
        fixture_payload=finished_fixture("future", NOW + timedelta(days=1)),
        statistics_payload=statistics(home_xg="9.9", away_xg="9.9"),
        captured_at=NOW,
        raw_payload_sha256="f" * 64,
    )

    snapshot = materialize_rolling_xg(
        team_id="10",
        as_of_fixture_id="target",
        as_of_time=NOW,
        matches=rows + future_rows,
        min_matches=3,
    )

    assert snapshot is not None
    assert snapshot.match_count == 4
    assert snapshot.rolling_xg_for < 9.9
    assert snapshot.as_feature_snapshot().observed_at == NOW


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        self.calls.append((endpoint, params))
        payload: dict[str, Any]
        if endpoint == "fixtures":
            team = params["team"]
            opponent = "20" if team == "10" else "10"
            payload = {
                "response": [
                    finished_fixture(
                        f"{team}-{index}",
                        NOW - timedelta(days=10 - index),
                        home=team,
                        away=opponent,
                    )
                    for index in range(5)
                ]
            }
        else:
            payload = statistics()
        return LiveApiFootballResponse(
            endpoint=endpoint,
            params=params,
            status_code=200,
            elapsed_ms=1,
            payload=payload,
            headers={"x-apisports-requests-remaining": "6000"},
            captured_at=NOW,
        )


class FakeRepository:
    def __init__(self) -> None:
        self.raw: list[tuple[str, str]] = []
        self.matches: list[dict[str, Any]] = []
        self.snapshots: list[dict[str, Any]] = []

    def fixture_payloads(self) -> list[dict[str, Any]]:
        return [
            {
                "fixture": {
                    "id": "target",
                    "date": (NOW + timedelta(days=1)).isoformat(),
                    "status": {"short": "NS"},
                },
                "league": {"id": 1, "season": "2026"},
                "teams": {"home": {"id": 10}, "away": {"id": 20}},
            },
            {
                "fixture": {
                    "id": "historical-raw-payload-must-not-pollute",
                    "date": (NOW - timedelta(days=2)).isoformat(),
                    "status": {"short": "FT"},
                },
                "league": {"id": 1, "season": "2026"},
                "teams": {"home": {"id": 30}, "away": {"id": 40}},
            },
            {
                "fixture": {
                    "id": "non-whitelisted-future",
                    "date": (NOW + timedelta(days=1)).isoformat(),
                    "status": {"short": "NS"},
                },
                "league": {"id": 999, "season": "2026"},
                "teams": {"home": {"id": 50}, "away": {"id": 60}},
            },
        ]

    def save_raw_payload(
        self,
        *,
        sha256: str,
        endpoint: str,
        captured_at: datetime,
        payload: dict[str, Any],
    ) -> str:
        self.raw.append((endpoint, sha256))
        return f"db://raw_payload/{sha256}"

    def upsert_team_xg_matches(self, matches: list[dict[str, Any]]) -> int:
        self.matches = matches
        return len(matches)

    def team_xg_matches(self) -> list[dict[str, Any]]:
        return self.matches

    def upsert_team_xg_rolling_snapshots(self, snapshots: list[dict[str, Any]]) -> int:
        self.snapshots = snapshots
        return len(snapshots)


def test_xg_backfill_uses_fake_provider_audits_and_materializes_snapshots() -> None:
    repository = FakeRepository()
    result = XgHistoryBackfillService(
        client=FakeClient(),
        repository=repository,
        config=XgBackfillConfig(request_budget=20, min_rolling_matches=3),
        now=NOW,
    ).run()

    assert result.team_count == 2
    assert result.statistics_request_count == 10
    assert result.team_xg_match_rows == 20
    assert result.rolling_snapshot_rows == 2
    assert result.remaining_quota == 6000
    assert result.candidate is False
    assert result.formal_recommendation is False
    assert {endpoint for endpoint, _ in repository.raw} == {"fixtures", "statistics"}
