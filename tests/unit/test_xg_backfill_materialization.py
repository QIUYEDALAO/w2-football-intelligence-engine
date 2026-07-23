from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from w2.features.xg_materialization import (
    materialize_rolling_xg,
    parse_team_xg_matches,
)
from w2.ingestion.xg_backfill import (
    XgBackfillConfig,
    XgHistoryBackfillService,
    run_xg_history_backfill,
)
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


class LowQuotaFakeClient(FakeClient):
    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        response = super().request_live(endpoint, params)
        return LiveApiFootballResponse(
            endpoint=response.endpoint,
            params=response.params,
            status_code=response.status_code,
            elapsed_ms=response.elapsed_ms,
            payload=response.payload,
            headers={"x-apisports-requests-remaining": "1499"},
            captured_at=response.captured_at,
        )


class ShortHistoryFakeClient(FakeClient):
    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        self.calls.append((endpoint, params))
        if endpoint == "fixtures":
            team = params["team"]
            opponent = "20" if team == "10" else "10"
            payload = {
                "response": [
                    finished_fixture(
                        f"{team}-new",
                        NOW - timedelta(days=1),
                        home=team,
                        away=opponent,
                    )
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
    def __init__(self, *, request_count_today: int = 0) -> None:
        self.raw: list[tuple[str, str]] = []
        self.matches: list[dict[str, Any]] = []
        self.snapshots: list[dict[str, Any]] = []
        self.request_count_today = request_count_today

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

    def request_count_since(self, since: datetime) -> int:
        return self.request_count_today


class ExistingXgRepository(FakeRepository):
    def __init__(self) -> None:
        super().__init__()
        self.existing_matches = [
            {
                "id": f"old-{team}-{index}:{team}",
                "fixture_id": f"old-{team}-{index}",
                "team_id": team,
                "opponent_team_id": "20" if team == "10" else "10",
                "kickoff_at": (NOW - timedelta(days=5 - index)).isoformat(),
                "captured_at": NOW.isoformat(),
                "xg_for": 1.0,
                "xg_against": 0.8,
                "goals_for": 1,
                "goals_against": 0,
                "raw_payload_sha256": f"{index}" * 64,
            }
            for team in ("10", "20")
            for index in range(2)
        ]

    def team_xg_matches(self) -> list[dict[str, Any]]:
        return [*self.existing_matches, *self.matches]


class MultiCompetitionRepository(FakeRepository):
    def fixture_payloads(self) -> list[dict[str, Any]]:
        return [
            {
                "fixture": {
                    "id": "allsvenskan-target",
                    "date": (NOW + timedelta(days=1)).isoformat(),
                    "status": {"short": "NS"},
                },
                "league": {"id": 113, "season": "2026"},
                "teams": {"home": {"id": 10}, "away": {"id": 20}},
            },
            {
                "fixture": {
                    "id": "world-cup-target",
                    "date": (NOW + timedelta(days=1)).isoformat(),
                    "status": {"short": "NS"},
                },
                "league": {"id": 1, "season": "2026"},
                "teams": {"home": {"id": 30}, "away": {"id": 40}},
            },
        ]


class BrokenUsageRepository(FakeRepository):
    def request_count_since(self, since: datetime) -> int:
        raise RuntimeError("usage audit unavailable")


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


def test_xg_backfill_competition_id_is_configurable(monkeypatch: Any) -> None:
    from w2.competitions.seed import set_competition_enabled
    from w2.infrastructure.database import create_engine

    monkeypatch.setenv("W2_ENVIRONMENT", "staging")
    monkeypatch.setenv("W2_XG_BACKFILL_COMPETITION_ID", "allsvenskan")
    monkeypatch.setenv("W2_XG_BACKFILL_REQUEST_BUDGET", "20")

    client = FakeClient()
    engine = create_engine()
    set_competition_enabled(
        engine,
        competition_id="allsvenskan",
        enabled=True,
        updated_by="xg-test",
    )
    try:
        result = run_xg_history_backfill(
            client=client,
            repository=MultiCompetitionRepository(),
            now=NOW,
        )
    finally:
        set_competition_enabled(
            engine,
            competition_id="allsvenskan",
            enabled=False,
            updated_by="xg-test-cleanup",
        )

    assert result.team_count == 2
    assert [call for call in client.calls if call[0] == "fixtures"] == [
        ("fixtures", {"team": "10", "last": "5"}),
        ("fixtures", {"team": "20", "last": "5"}),
    ]


def test_xg_backfill_rolls_forward_existing_persisted_xg_matches() -> None:
    repository = ExistingXgRepository()
    result = XgHistoryBackfillService(
        client=ShortHistoryFakeClient(),
        repository=repository,
        config=XgBackfillConfig(request_budget=20, min_rolling_matches=3),
        now=NOW,
    ).run()

    assert result.team_xg_match_rows == 4
    assert result.rolling_snapshot_rows == 2


def test_xg_backfill_stops_before_consuming_live_reserve() -> None:
    client = LowQuotaFakeClient()
    repository = FakeRepository()

    result = XgHistoryBackfillService(
        client=client,
        repository=repository,
        config=XgBackfillConfig(request_budget=20, quota_reserve=1500),
        now=NOW,
    ).run()

    assert result.blockers == ["BACKFILL_QUOTA_GUARD"]
    assert result.remaining_quota == 1499
    assert len(client.calls) == 1
    assert client.calls[0][0] == "fixtures"
    assert all(endpoint != "statistics" for endpoint, _ in client.calls)
    assert repository.raw == []


def test_xg_backfill_daily_hard_cap_blocks_before_provider_call() -> None:
    client = FakeClient()
    repository = FakeRepository(request_count_today=6000)

    result = XgHistoryBackfillService(
        client=client,
        repository=repository,
        config=XgBackfillConfig(
            request_budget=120,
            daily_hard_cap=7500,
            daily_reserve=1500,
        ),
        now=NOW,
    ).run()

    assert result.blockers == ["PROVIDER_RESERVE_PROTECTED"]
    assert result.statistics_request_count == 0
    assert result.as_dict()["provider_calls"] == 0
    assert client.calls == []
    assert repository.raw == []
    assert repository.matches == []
    assert repository.snapshots == []
    assert result.requests[0]["error_code"] == "PROVIDER_RESERVE_PROTECTED"


def test_xg_backfill_fails_closed_when_provider_usage_audit_unavailable() -> None:
    client = FakeClient()
    repository = BrokenUsageRepository()

    result = XgHistoryBackfillService(
        client=client,
        repository=repository,
        config=XgBackfillConfig(
            request_budget=120,
            daily_hard_cap=7500,
            daily_reserve=1500,
        ),
        now=NOW,
    ).run()

    assert result.blockers == ["PROVIDER_USAGE_AUDIT_UNAVAILABLE"]
    assert result.statistics_request_count == 0
    assert result.as_dict()["provider_calls"] == 0
    assert client.calls == []
    assert repository.raw == []
    assert repository.matches == []
    assert repository.snapshots == []
    assert result.requests[0]["error_code"] == "PROVIDER_USAGE_AUDIT_UNAVAILABLE"
