from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from w2.ingestion.future_refresh import (
    FutureFixtureRefreshService,
    FutureRefreshConfig,
    FutureRefreshError,
)
from w2.providers.api_football import LiveApiFootballResponse

NOW = datetime(2026, 6, 23, 10, 0, tzinfo=UTC)


class FakeApiFootballClient:
    def __init__(self, *, remaining: int = 7000) -> None:
        self.remaining = remaining
        self.calls: list[tuple[str, dict[str, str]]] = []

    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        self.calls.append((endpoint, params))
        payload = self.payload(endpoint, params)
        return LiveApiFootballResponse(
            endpoint=endpoint,
            params=params,
            status_code=200,
            elapsed_ms=7,
            payload=payload,
            headers={"x-ratelimit-requests-remaining": str(self.remaining)},
            captured_at=NOW,
        )

    def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint == "status":
            return {"response": {"requests": {"remaining": self.remaining}}}
        if endpoint == "fixtures":
            return {
                "response": [
                    {
                        "fixture": {
                            "id": 1489404,
                            "date": "2026-06-23T17:00:00+00:00",
                            "status": {"short": "NS"},
                            "venue": {"name": "Test Venue"},
                        },
                        "league": {"id": 1, "name": "World Cup", "round": "Group K"},
                        "teams": {
                            "home": {"id": 10, "name": "Team A"},
                            "away": {"id": 20, "name": "Team B"},
                        },
                    },
                    {
                        "fixture": {
                            "id": 1480000,
                            "date": "2026-06-22T17:00:00+00:00",
                            "status": {"short": "NS"},
                        },
                        "league": {"id": 1, "name": "World Cup"},
                        "teams": {"home": {"id": 1}, "away": {"id": 2}},
                    },
                ]
            }
        if endpoint == "odds":
            return {
                "response": [
                    {
                        "fixture": {"id": int(params["fixture"])},
                        "bookmakers": [
                            {
                                "id": 1,
                                "name": "Book A",
                                "bets": [{"id": 1, "name": "Match Winner"}],
                            },
                            {
                                "id": 2,
                                "name": "Book B",
                                "bets": [{"id": 1, "name": "Match Winner"}],
                            },
                        ],
                    }
                ]
            }
        raise AssertionError(endpoint)


def test_future_fixture_refresh_writes_idempotent_read_model(tmp_path: Path) -> None:
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(runtime_root=tmp_path, quota_reserve=1500)
    service = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    )

    first = service.run()
    second = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()

    assert first.fixture_count == 1
    assert first.mapping_count == 1
    assert first.market_snapshot_count == 1
    assert second.fixture_count == 1
    assert (tmp_path / "read_model/fixtures.json").is_file()
    assert (tmp_path / "read_model/provider_mappings.json").is_file()
    assert (tmp_path / "read_model/market_snapshots.json").is_file()
    assert len(list((tmp_path / "raw").glob("fixtures_*.json"))) == 1
    assert len(list((tmp_path / "raw").glob("odds_*.json"))) == 1


def test_future_fixture_refresh_blocks_low_quota(tmp_path: Path) -> None:
    client = FakeApiFootballClient(remaining=1499)
    config = FutureRefreshConfig(runtime_root=tmp_path, quota_reserve=1500)
    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()

    assert result.blockers == ["QUOTA_BELOW_RESERVE"]
    assert result.fixture_count == 0
    assert (tmp_path / "future_refresh_audit.json").is_file()


def test_future_fixture_refresh_request_budget(tmp_path: Path) -> None:
    client = FakeApiFootballClient()
    config = FutureRefreshConfig(runtime_root=tmp_path, request_budget=1)
    result = FutureFixtureRefreshService(
        client=client,
        config=config,
        now=NOW,
        sleep=lambda _: None,
    ).run()

    assert result.blockers == ["REQUEST_BUDGET_EXHAUSTED"]
    assert len(client.calls) == 1


def test_future_refresh_error_type_is_runtime_error() -> None:
    assert issubclass(FutureRefreshError, RuntimeError)
