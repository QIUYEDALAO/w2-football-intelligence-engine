from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from w2.ingestion.independent_signal_backfill import (
    IndependentSignalBackfillConfig,
    IndependentSignalBackfillService,
)
from w2.prematch import analysis_calculator as api_repository
from w2.prematch.analysis_calculator import ReadModelService
from w2.providers.api_football import LiveApiFootballResponse


class FixtureProvider:
    def fixture_payloads(self) -> list[dict[str, Any]]:
        return [
            {
                "fixture": {
                    "id": "future-1",
                    "date": "2026-07-10T18:00:00Z",
                    "status": {"short": "NS"},
                },
                "league": {"id": 1, "name": "World Cup"},
                "teams": {
                    "home": {"id": 10, "name": "Strong"},
                    "away": {"id": 20, "name": "Weak"},
                },
            }
        ]

    def matchday_cards(self) -> list[dict[str, Any]]:
        return []

    def dashboard_fixture(self, fixture_id: str) -> dict[str, Any] | None:
        return None

    def future_market_observations(self) -> list[dict[str, Any]]:
        captured = "2026-07-01T12:00:00Z"
        return [
            {
                "fixture_id": "future-1",
                "canonical_market": "ASIAN_HANDICAP",
                "selection": "Home",
                "line": "0",
                "decimal_odds": "1.91",
                "captured_at": captured,
                "provider_last_update": captured,
                "bookmaker_id": "bm1",
                "bookmaker_name": "Book",
                "suspended": False,
                "live": False,
            },
            {
                "fixture_id": "future-1",
                "canonical_market": "ASIAN_HANDICAP",
                "selection": "Away",
                "line": "0",
                "decimal_odds": "1.91",
                "captured_at": captured,
                "provider_last_update": captured,
                "bookmaker_id": "bm1",
                "bookmaker_name": "Book",
                "suspended": False,
                "live": False,
            },
        ]


class FakeIndependentSignalClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def fixtures_by_team(
        self,
        *,
        team_id: str,
        season: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> LiveApiFootballResponse:
        self.calls.append(("fixtures", {"team": team_id, "season": season}))
        if team_id == "10":
            rows = [
                api_fixture("h10-1", "2026-06-20T18:00:00Z", "10", "30", 4, 0),
                api_fixture("h10-2", "2026-06-25T18:00:00Z", "40", "10", 0, 2),
            ]
        else:
            rows = [
                api_fixture("h20-1", "2026-06-19T18:00:00Z", "20", "50", 0, 2),
                api_fixture("h20-2", "2026-06-24T18:00:00Z", "60", "20", 3, 0),
            ]
        return response(endpoint="fixtures", params={"team": team_id}, rows=rows)

    def h2h(
        self,
        *,
        team_a_id: str,
        team_b_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> LiveApiFootballResponse:
        self.calls.append(("h2h", {"h2h": f"{team_a_id}-{team_b_id}"}))
        return response(
            endpoint="h2h",
            params={"h2h": f"{team_a_id}-{team_b_id}"},
            rows=[api_fixture("h2h-1", "2026-06-01T18:00:00Z", team_a_id, team_b_id, 3, 0)],
        )


def api_fixture(
    fixture_id: str,
    date: str,
    home_id: str,
    away_id: str,
    home_goals: int,
    away_goals: int,
) -> dict[str, Any]:
    return {
        "fixture": {"id": fixture_id, "date": date, "status": {"short": "FT"}},
        "teams": {
            "home": {"id": int(home_id), "name": f"Team {home_id}"},
            "away": {"id": int(away_id), "name": f"Team {away_id}"},
        },
        "goals": {"home": home_goals, "away": away_goals},
    }


def response(
    *,
    endpoint: str,
    params: dict[str, str],
    rows: list[dict[str, Any]],
) -> LiveApiFootballResponse:
    return LiveApiFootballResponse(
        endpoint=endpoint,
        params=params,
        status_code=200,
        elapsed_ms=1,
        payload={"response": rows},
        headers={"x-ratelimit-requests-remaining": "6774"},
        captured_at=datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
    )


def config(**overrides: Any) -> IndependentSignalBackfillConfig:
    values: dict[str, Any] = {
        "task": "team_fixture_history_backfill",
        "competition_id": "world_cup_2026",
        "season": "2026",
        "window": "all",
        "dry_run": True,
        "write_artifacts": False,
        "remaining_quota_override": 6774,
    }
    values.update(overrides)
    return IndependentSignalBackfillConfig(**values)


def service(client: FakeIndependentSignalClient) -> IndependentSignalBackfillService:
    return IndependentSignalBackfillService(
        fixture_provider=FixtureProvider(),
        client=client,
        now=datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
    )


def test_dry_run_does_not_call_provider() -> None:
    client = FakeIndependentSignalClient()

    result = service(client).run(config(dry_run=True, write_artifacts=True))

    assert result["status"] == "ok"
    assert result["dry_run"] is True
    assert result["provider_calls"] == 0
    assert client.calls == []


def test_quota_blocked_does_not_call_provider() -> None:
    client = FakeIndependentSignalClient()

    result = service(client).run(
        config(dry_run=False, write_artifacts=True, remaining_quota_override=1499)
    )

    assert result["status"] == "blocked"
    assert result["quota_decision"]["reason"] == "BACKFILL_QUOTA_GUARD"
    assert result["provider_calls"] == 0
    assert client.calls == []


def test_write_artifacts_only_when_explicitly_requested(tmp_path: Any) -> None:
    client = FakeIndependentSignalClient()

    result = service(client).run(
        config(dry_run=False, write_artifacts=False, runtime_root=tmp_path)
    )

    assert result["status"] == "ok"
    assert result["provider_calls"] == 0
    assert not list(tmp_path.rglob("*.json"))

    written = service(client).run(
        config(dry_run=False, write_artifacts=True, runtime_root=tmp_path)
    )

    assert written["provider_calls"] == 2
    assert written["artifacts_written"] == 2
    assert list((tmp_path / "raw_payloads/fixtures").glob("*.json"))


def test_h2h_backfill_writes_artifact(tmp_path: Any) -> None:
    client = FakeIndependentSignalClient()

    result = service(client).run(
        config(task="h2h_backfill", dry_run=False, write_artifacts=True, runtime_root=tmp_path)
    )

    assert result["provider_calls"] == 1
    assert result["artifacts_written"] == 1
    assert list((tmp_path / "raw_payloads/h2h").glob("*.json"))


def test_repository_consumes_generated_artifacts(monkeypatch: Any, tmp_path: Any) -> None:
    client = FakeIndependentSignalClient()
    runtime_root = tmp_path / "runtime/independent_signal_backfill"
    service(client).run(
        config(dry_run=False, write_artifacts=True, runtime_root=runtime_root)
    )
    service(client).run(
        config(
            task="h2h_backfill",
            dry_run=False,
            write_artifacts=True,
            runtime_root=runtime_root,
        )
    )
    monkeypatch.setattr(api_repository, "ROOT", tmp_path)
    monkeypatch.setattr(api_repository, "future_refresh_db_repository", lambda: None)

    card = ReadModelService(repository=cast(Any, FixtureProvider())).analysis_card("future-1")

    assert card is not None
    summary = card["pricing_shadow"]["factor_source_summary"]
    assert summary["F3_REST_FITNESS"]["source_group"] == "team_fixture_history"
    assert summary["F6_H2H"]["source_group"] == "h2h"
    assert summary["F7_STRENGTH_FORM"]["source_group"] == "ratings"
    assert card["pricing_shadow"]["independent_signal_count"] >= 3


def test_repository_skips_unreadable_runtime_artifacts(monkeypatch: Any, tmp_path: Any) -> None:
    raw_dir = tmp_path / "runtime/independent_signal_backfill/raw_payloads/fixtures"
    raw_dir.mkdir(parents=True)
    monkeypatch.setattr(api_repository, "ROOT", tmp_path)
    original_glob = Path.glob

    def unreadable_glob(path: Any, pattern: str) -> Any:
        if "independent_signal_backfill" in str(path):
            raise PermissionError("permission denied")
        return original_glob(path, pattern)

    monkeypatch.setattr(Path, "glob", unreadable_glob)

    rows = ReadModelService(
        repository=cast(Any, FixtureProvider())
    )._fixture_response_items_from_runtime_artifacts(endpoint="fixtures")

    assert rows == []


def test_repository_skips_runtime_artifacts_when_exists_is_unreadable(
    monkeypatch: Any, tmp_path: Any
) -> None:
    raw_dir = tmp_path / "runtime/independent_signal_backfill/raw_payloads/fixtures"
    raw_dir.mkdir(parents=True)
    monkeypatch.setattr(api_repository, "ROOT", tmp_path)
    original_exists = Path.exists

    def unreadable_exists(path: Any) -> bool:
        if "independent_signal_backfill" in str(path):
            raise PermissionError("permission denied")
        return bool(original_exists(path))

    monkeypatch.setattr(Path, "exists", unreadable_exists)

    rows = ReadModelService(
        repository=cast(Any, FixtureProvider())
    )._fixture_response_items_from_runtime_artifacts(endpoint="fixtures")

    assert rows == []


def test_repository_skips_unreadable_runtime_artifact_file(
    monkeypatch: Any, tmp_path: Any
) -> None:
    raw_dir = tmp_path / "runtime/independent_signal_backfill/raw_payloads/fixtures"
    raw_dir.mkdir(parents=True)
    artifact = raw_dir / "team_10.json"
    artifact.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(api_repository, "ROOT", tmp_path)

    def unreadable_load_json(path: Any, default: Any) -> Any:
        if path == artifact:
            raise PermissionError("permission denied")
        return default

    monkeypatch.setattr(api_repository, "load_json", unreadable_load_json)

    rows = ReadModelService(
        repository=cast(Any, FixtureProvider())
    )._fixture_response_items_from_runtime_artifacts(endpoint="fixtures")

    assert rows == []
