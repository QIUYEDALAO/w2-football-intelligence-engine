from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from scripts.backfill_factor_history_fixtures import (
    BACKFILL_LOGICAL_REQUEST_CAP,
    BackfillConfig,
    BackfillScope,
    HistoricalFixtureBackfillService,
)

from w2.providers.api_football import LiveApiFootballResponse


def _scopes() -> tuple[BackfillScope, ...]:
    return tuple(
        BackfillScope(
            competition_id=f"competition_{index}",
            provider_league_id=str(100 + index),
            season=season,
        )
        for index in range(13)
        for season in ("2022", "2023")
    )


class _Repository:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]:
        assert endpoint == "fixtures"
        return list(self.rows)

    def raw_payload_exists(self, *, sha256: str, endpoint: str) -> bool:
        return any(row["sha256"] == sha256 and row["endpoint"] == endpoint for row in self.rows)

    def save_raw_payload(self, **kwargs: Any) -> str:
        if not self.raw_payload_exists(
            sha256=str(kwargs["sha256"]), endpoint=str(kwargs["endpoint"])
        ):
            self.rows.append(dict(kwargs))
        return f"db://raw_payload/{kwargs['sha256']}"

    def request_count_since(self, since: datetime) -> int:
        assert since.tzinfo is not None
        return 100


class _Client:
    def __init__(self, *, timeout_once: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.timeout_once = timeout_once

    def request_live(
        self, endpoint: str, params: dict[str, str]
    ) -> LiveApiFootballResponse:
        self.calls.append((endpoint, params))
        if self.timeout_once:
            self.timeout_once = False
            raise TimeoutError
        league_id = params["league"]
        season = params["season"]
        captured_at = datetime(2026, 8, 24, 1, tzinfo=UTC)
        return LiveApiFootballResponse(
            endpoint=endpoint,
            params=params,
            status_code=200,
            elapsed_ms=500,
            payload={
                "parameters": dict(params),
                "errors": {},
                "results": 1,
                "response": [
                    {
                        "fixture": {
                            "id": int(f"{league_id}{season}"),
                            "date": f"{season}-01-01T12:00:00+00:00",
                        },
                        "league": {"id": int(league_id), "season": int(season)},
                        "teams": {"home": {"id": 1}, "away": {"id": 2}},
                    }
                ],
            },
            headers={"x-apisports-requests-remaining": "7000"},
            captured_at=captured_at,
        )


def _service(
    *,
    repository: _Repository,
    client: _Client,
    current: datetime,
    active_plans: list[dict[str, Any]] | None = None,
) -> HistoricalFixtureBackfillService:
    return HistoricalFixtureBackfillService(
        scopes=_scopes(),
        repository=repository,
        client=client,
        config=BackfillConfig(),
        now=lambda: current,
        sleep=lambda _seconds: None,
        quiet_guard=lambda _as_of: list(active_plans or []),
        runtime_hardening_guard=lambda: None,
    )


def test_plan_is_exact_26_and_provider_zero() -> None:
    repository = _Repository()
    client = _Client()

    report = _service(
        repository=repository,
        client=client,
        current=datetime(2026, 8, 22, 1, tzinfo=UTC),
    ).run(live=False)

    assert report["scope_count"] == BACKFILL_LOGICAL_REQUEST_CAP == 26
    assert report["endpoint_allowlist"] == ["fixtures"]
    assert report["protected_near_match_checkpoints"] == [
        "T60_ODDS_LINEUPS",
        "T45_ODDS",
        "T45_LINEUPS_RETRY",
        "T-30m_VALIDATION_LOCK",
        "T30_LINEUPS_RETRY",
        "T15_ODDS",
    ]
    assert report["worst_case_pending_seconds"] == 2417
    assert report["quiet_window_reserve_seconds"] == 1183
    assert report["provider_calls"] == 0
    assert client.calls == []
    assert repository.rows == []


def test_weekend_live_execution_is_hard_blocked() -> None:
    repository = _Repository()
    client = _Client()

    report = _service(
        repository=repository,
        client=client,
        current=datetime(2026, 8, 23, 23, 59, tzinfo=UTC),
    ).run(live=True)

    assert report["blockers"] == ["WEEKEND_BACKFILL_FORBIDDEN"]
    assert client.calls == []
    assert repository.rows == []


def test_owner_authorized_quiet_window_is_limited_to_august_22_before_09z() -> None:
    repository = _Repository()
    client = _Client()

    report = _service(
        repository=repository,
        client=client,
        current=datetime(2026, 8, 22, 5, 45, tzinfo=UTC),
    ).run(live=True, owner_authorized_2026_08_22_quiet_window=True)

    assert report["blockers"] == []
    assert report["logical_request_count"] == 26

    blocked = _service(
        repository=_Repository(),
        client=_Client(),
        current=datetime(2026, 8, 22, 9, tzinfo=UTC),
    ).run(live=True, owner_authorized_2026_08_22_quiet_window=True)
    assert blocked["blockers"] == ["WEEKEND_BACKFILL_FORBIDDEN"]


def test_active_matchday_window_blocks_before_provider_call() -> None:
    repository = _Repository()
    client = _Client()

    report = _service(
        repository=repository,
        client=client,
        current=datetime(2026, 8, 24, 1, tzinfo=UTC),
        active_plans=[{"plan_id": "p1"}],
    ).run(live=True)

    assert report["blockers"] == ["MATCHDAY_CHECKPOINT_WINDOW_OVERLAP"]
    assert client.calls == []
    assert repository.rows == []


def test_live_backfill_uses_only_fixtures_and_retries_one_timeout() -> None:
    repository = _Repository()
    client = _Client(timeout_once=True)

    report = _service(
        repository=repository,
        client=client,
        current=datetime(2026, 8, 24, 1, tzinfo=UTC),
    ).run(live=True)

    assert report["blockers"] == []
    assert report["logical_request_count"] == 26
    assert report["physical_attempt_count"] == 27
    assert report["raw_payloads_added"] == 26
    assert {endpoint for endpoint, _params in client.calls} == {"fixtures"}
    assert {frozenset(params) for _endpoint, params in client.calls} == {
        frozenset({"league", "season"})
    }
    assert {str(row["payload"]["parameters"]["season"]) for row in repository.rows} == {
        "2022",
        "2023",
    }
