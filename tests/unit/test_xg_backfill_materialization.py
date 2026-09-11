from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from w2.features.xg_materialization import (
    materialize_rolling_xg,
    parse_team_xg_matches,
)
from w2.ingestion.xg_backfill import (
    ProStatisticsBackfillConfig,
    ProStatisticsBackfillService,
    XgBackfillConfig,
    XgBackfillError,
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
    league_id: int = 113,
    season: str = "2026",
) -> dict[str, Any]:
    return {
        "fixture": {
            "id": fixture_id,
            "date": kickoff.isoformat().replace("+00:00", "Z"),
            "status": {"short": "FT"},
        },
        "league": {"id": league_id, "season": season},
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
                captured_at=NOW - timedelta(hours=1),
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
    assert snapshot.as_feature_snapshot().observed_at == NOW - timedelta(hours=1)


def test_rolling_xg_visibility_uses_latest_component_availability() -> None:
    rows = []
    captured_times = (
        NOW - timedelta(hours=4),
        NOW - timedelta(hours=3),
        NOW - timedelta(hours=2),
    )
    for index, captured_at in enumerate(captured_times):
        rows.extend(
            parse_team_xg_matches(
                fixture_payload=finished_fixture(
                    f"available-{index}", NOW - timedelta(days=3 - index)
                ),
                statistics_payload=statistics(),
                captured_at=captured_at,
                raw_payload_sha256=f"{index + 1}" * 64,
            )
        )

    snapshot = materialize_rolling_xg(
        team_id="10",
        as_of_fixture_id="future-target",
        as_of_time=NOW + timedelta(days=7),
        matches=rows,
        min_matches=3,
    )

    assert snapshot is not None
    assert snapshot.as_of_time == captured_times[-1]
    assert snapshot.as_of_time < NOW


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
                "league": {"id": 113, "season": "2026"},
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

    def raw_payload_count(self, endpoint: str) -> int:
        return sum(saved_endpoint == endpoint for saved_endpoint, _digest in self.raw)

    def raw_payload_exists(self, *, sha256: str, endpoint: str) -> bool:
        return (endpoint, sha256) in self.raw

    def raw_statistics_fixture_ids(self) -> set[str]:
        return set()

    def provider_live_request_count_since(self, *, endpoint: str, since: datetime) -> int:
        return int(getattr(self, "statistics_request_count_today", 0))

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

    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]:
        return []

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

    def provider_team_mapping(
        self,
        *,
        provider: str,
        competition_id: str,
        season: str,
        as_of: datetime,
    ) -> dict[str, str]:
        assert provider == "api_football"
        assert competition_id == "allsvenskan"
        assert season == "2026"
        return {team_id: f"w2:team:api_football:{team_id}" for team_id in ("10", "20")}


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


class SavedRawRepository(FakeRepository):
    def fixture_payloads(self) -> list[dict[str, Any]]:
        rows = super().fixture_payloads()
        for index in range(4):
            item = finished_fixture(
                f"saved-{index}",
                NOW - timedelta(days=5 - index),
            )
            item["league"] = {"id": 113, "season": "2026"}
            rows.append(item)
        return rows

    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]:
        assert endpoint == "statistics"
        return [
            {
                "sha256": f"{index}" * 64,
                "captured_at": NOW.isoformat(),
                "payload": {
                    **statistics(home_xg=str(1.2 + index / 10), away_xg="0.8"),
                    "parameters": {"fixture": f"saved-{index}"},
                },
            }
            for index in range(4)
        ]


class NoCallClient(FakeClient):
    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        raise AssertionError("saved-raw materialization must not call Provider")


class ShortSavedRawRepository(SavedRawRepository):
    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]:
        return super().raw_payloads(endpoint)[:2]


class ConflictingSavedRawRepository(SavedRawRepository):
    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]:
        rows = super().raw_payloads(endpoint)
        rows.append(
            {
                "sha256": "f" * 64,
                "captured_at": NOW.isoformat(),
                "payload": {
                    **statistics(home_xg="9.9", away_xg="0.8"),
                    "parameters": {"fixture": "saved-0"},
                },
            }
        )
        return rows


class NoCanonicalSavedRawRepository(SavedRawRepository):
    def provider_team_mapping(
        self,
        *,
        provider: str,
        competition_id: str,
        season: str,
        as_of: datetime,
    ) -> dict[str, str]:
        return {}


def test_saved_statistics_raw_materializes_xg_and_is_idempotent() -> None:
    repository = SavedRawRepository()
    service = XgHistoryBackfillService(
        client=NoCallClient(),
        repository=repository,
        config=XgBackfillConfig(min_rolling_matches=3),
        now=NOW,
    )

    first = service.run_saved_raw()
    second = service.run_saved_raw()

    assert first.as_dict()["provider_calls"] == 0
    assert first.team_xg_match_rows == 8
    assert first.rolling_snapshot_rows == 2
    assert second.team_xg_match_rows == 0
    assert second.rolling_snapshot_rows == 2


def test_saved_statistics_raw_materializes_registered_historical_season() -> None:
    repository = SavedRawRepository()
    for fixture in repository.fixture_payloads():
        if str(fixture.get("fixture", {}).get("id", "")).startswith("saved-"):
            fixture["league"] = {"id": 113, "season": "2024"}

    result = XgHistoryBackfillService(
        client=NoCallClient(),
        repository=repository,
        config=XgBackfillConfig(min_rolling_matches=3),
        now=NOW,
    ).run_saved_raw()

    assert result.team_xg_match_rows == 8


def test_history_fetch_rejects_finished_fixture_outside_registered_leagues() -> None:
    service = XgHistoryBackfillService(
        client=NoCallClient(),
        repository=SavedRawRepository(),
        config=XgBackfillConfig(min_rolling_matches=3),
        now=NOW,
    )
    payload = {
        "response": [
            finished_fixture("target", NOW - timedelta(days=1)),
            finished_fixture("cup", NOW - timedelta(days=1), league_id=171),
        ]
    }

    assert [row["fixture"]["id"] for row in service._finished_fixture_items(payload)] == ["target"]


def test_saved_raw_rebuild_uses_snapshot_identities_not_current_mapping() -> None:
    plan = XgHistoryBackfillService(
        client=NoCallClient(),
        repository=NoCanonicalSavedRawRepository(),
        config=XgBackfillConfig(min_rolling_matches=3),
        now=NOW,
    ).build_saved_raw_plan(
        snapshot_identities=[
            {
                "snapshot_id": f"{team_id}:target",
                "team_id": team_id,
                "as_of_fixture_id": "target",
            }
            for team_id in ("10", "20")
        ]
    )

    assert len(plan.team_xg_matches) == 8
    assert len(plan.rolling_snapshots) == 2
    assert plan.blockers == ()


def test_saved_statistics_raw_dry_run_is_exact13_canonical_and_write_free() -> None:
    repository = SavedRawRepository()
    result = XgHistoryBackfillService(
        client=NoCallClient(),
        repository=repository,
        config=XgBackfillConfig(min_rolling_matches=3),
        now=NOW,
    ).run_saved_raw(persist=False)

    assert result.dry_run is True
    assert result.as_dict()["provider_calls"] == 0
    assert result.team_xg_match_rows == 8
    assert result.rolling_snapshot_rows == 2
    assert repository.matches == []
    assert repository.snapshots == []


def test_saved_statistics_raw_with_less_than_three_matches_has_no_snapshot() -> None:
    repository = ShortSavedRawRepository()
    result = XgHistoryBackfillService(
        client=NoCallClient(),
        repository=repository,
        config=XgBackfillConfig(min_rolling_matches=3),
        now=NOW,
    ).run_saved_raw()

    assert result.team_xg_match_rows == 4
    assert result.rolling_snapshot_rows == 0


def test_saved_statistics_raw_conflict_fails_closed() -> None:
    repository = ConflictingSavedRawRepository()

    with pytest.raises(XgBackfillError, match="SAVED_XG_CONFLICT:saved-0:10"):
        XgHistoryBackfillService(
            client=NoCallClient(),
            repository=repository,
            config=XgBackfillConfig(min_rolling_matches=3),
            now=NOW,
        ).run_saved_raw()

    assert repository.matches == []
    assert repository.snapshots == []


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


def test_xg_backfill_statistics_daily_cap_stops_statistics_calls() -> None:
    client = FakeClient()
    repository = FakeRepository()
    repository.statistics_request_count_today = 5500

    result = XgHistoryBackfillService(
        client=client,
        repository=repository,
        config=XgBackfillConfig(
            request_budget=120,
            statistics_daily_hard_cap=5500,
        ),
        now=NOW,
    ).run()

    assert result.blockers == ["STATISTICS_DAILY_HARD_CAP_REACHED"]
    assert result.statistics_request_count == 0
    assert all(endpoint != "statistics" for endpoint, _params in client.calls)


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


class ProBackfillRepository(FakeRepository):
    def __init__(self, fixtures: list[dict[str, Any]]) -> None:
        super().__init__()
        self.fixtures = fixtures

    def fixture_payloads(self) -> list[dict[str, Any]]:
        return self.fixtures

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


class ProBackfillClient:
    def __init__(self, *, with_xg: bool = True) -> None:
        self.calls: list[str] = []
        self.with_xg = with_xg

    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        fixture_id = params["fixture"]
        self.calls.append(fixture_id)
        payload = statistics() if self.with_xg else {"response": []}
        payload["parameters"] = {"fixture": fixture_id}
        return LiveApiFootballResponse(
            endpoint=endpoint,
            params=params,
            status_code=200,
            elapsed_ms=1,
            payload=payload,
            headers={"x-ratelimit-requests-remaining": "7000"},
            captured_at=NOW,
        )


def pro_fixture(fixture_id: str, *, league_id: int) -> dict[str, Any]:
    fixture = finished_fixture(fixture_id, NOW - timedelta(days=1))
    fixture["league"] = {"id": league_id, "season": "2024"}
    return fixture


def test_pro_statistics_backfill_persists_missing_fixture_manifests(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr("w2.ingestion.xg_backfill.time.sleep", lambda _seconds: None)
    repository = ProBackfillRepository([])

    class ManifestClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, str]]] = []

        def request_live(
            self,
            endpoint: str,
            params: dict[str, str],
        ) -> LiveApiFootballResponse:
            self.calls.append((endpoint, params))
            return LiveApiFootballResponse(
                endpoint=endpoint,
                params=params,
                status_code=200,
                elapsed_ms=1,
                payload={"parameters": params, "response": []},
                headers={"x-ratelimit-requests-remaining": "7000"},
                captured_at=NOW,
            )

    client = ManifestClient()
    result = ProStatisticsBackfillService(
        client=client,
        repository=repository,
        config=ProStatisticsBackfillConfig(batch=3, request_budget=10),
        now=NOW,
    ).run()

    assert result.fixture_manifest_request_count == 6
    assert result.raw_fixtures_added == 6
    assert {endpoint for endpoint, _params in client.calls} == {"fixtures"}
    assert {params["season"] for _endpoint, params in client.calls} == {
        "2024",
        "2025",
        "2026",
    }


def test_pro_statistics_backfill_persists_each_response_with_count_and_hash_guard(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr("w2.ingestion.xg_backfill.time.sleep", lambda _seconds: None)
    repository = ProBackfillRepository(
        [pro_fixture("br-1", league_id=71), pro_fixture("br-2", league_id=71)]
    )
    client = ProBackfillClient()

    result = ProStatisticsBackfillService(
        client=client,
        repository=repository,
        config=ProStatisticsBackfillConfig(
            batch=1,
            request_budget=10,
            ensure_fixture_manifests=False,
        ),
        now=NOW,
    ).run()

    assert client.calls == ["br-1", "br-2"]
    assert result.raw_statistics_added == 2
    assert result.raw_statistics_before == 0
    assert result.raw_statistics_after == 2
    assert len(result.raw_payload_sha256) == 2
    assert result.remaining_fixture_count == 0


def test_pro_statistics_backfill_stops_scope_after_empty_xg_pilot(monkeypatch: Any) -> None:
    monkeypatch.setattr("w2.ingestion.xg_backfill.time.sleep", lambda _seconds: None)
    repository = ProBackfillRepository(
        [pro_fixture(f"pl-{index}", league_id=39) for index in range(5)]
    )
    client = ProBackfillClient(with_xg=False)

    result = ProStatisticsBackfillService(
        client=client,
        repository=repository,
        config=ProStatisticsBackfillConfig(
            batch=2,
            request_budget=10,
            ensure_fixture_manifests=False,
        ),
        now=NOW,
    ).run()

    assert client.calls == ["pl-0", "pl-1", "pl-2"]
    assert result.raw_statistics_added == 3
    assert result.skipped_competitions == ("premier_league",)
    assert result.blockers == ("PRO_STATISTICS_XG_PILOT_EMPTY:premier_league",)


def test_pro_statistics_backfill_continues_after_one_scope_fails_pilot(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr("w2.ingestion.xg_backfill.time.sleep", lambda _seconds: None)
    repository = ProBackfillRepository(
        [pro_fixture(f"de-{index}", league_id=78) for index in range(3)]
        + [pro_fixture(f"pl-{index}", league_id=39) for index in range(3)]
    )
    client = ProBackfillClient()
    original_request = client.request_live

    def request_live(endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        response = original_request(endpoint, params)
        if params["fixture"].startswith("de-"):
            response.payload["response"] = []
        return response

    monkeypatch.setattr(client, "request_live", request_live)

    result = ProStatisticsBackfillService(
        client=client,
        repository=repository,
        config=ProStatisticsBackfillConfig(
            batch=2,
            request_budget=10,
            ensure_fixture_manifests=False,
        ),
        now=NOW,
    ).run()

    assert client.calls == ["de-0", "de-1", "de-2", "pl-0", "pl-1", "pl-2"]
    assert result.skipped_competitions == ("bundesliga",)
    assert "premier_league" in result.pilot_xg_verified_competitions


def test_pro_statistics_backfill_verifies_all_pilots_before_bulk(monkeypatch: Any) -> None:
    monkeypatch.setattr("w2.ingestion.xg_backfill.time.sleep", lambda _seconds: None)
    repository = ProBackfillRepository(
        [pro_fixture(f"de-{index}", league_id=78) for index in range(4)]
        + [pro_fixture(f"pl-{index}", league_id=39) for index in range(4)]
    )
    client = ProBackfillClient()

    ProStatisticsBackfillService(
        client=client,
        repository=repository,
        config=ProStatisticsBackfillConfig(
            batch=2,
            request_budget=8,
            ensure_fixture_manifests=False,
        ),
        now=NOW,
    ).run()

    assert client.calls == [
        "de-0",
        "de-1",
        "de-2",
        "pl-0",
        "pl-1",
        "pl-2",
        "de-3",
        "pl-3",
    ]
