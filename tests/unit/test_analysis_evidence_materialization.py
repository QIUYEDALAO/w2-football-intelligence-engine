from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any, cast

from w2.api.repository import ReadModelRepository, ReadModelService


class _Repository:
    def __init__(self) -> None:
        self.persisted: list[dict[str, Any]] = []

    def fixture_payloads(self) -> list[dict[str, Any]]:
        return [
            {
                "fixture": {
                    "id": "fixture-1",
                    "date": "2099-01-01T10:00:00Z",
                    "status": {"short": "NS"},
                },
                "league": {"id": "71", "name": "League"},
                "teams": {
                    "home": {"id": "home", "name": "Home"},
                    "away": {"id": "away", "name": "Away"},
                },
            }
        ]

    def future_market_observations_for_fixtures(
        self, fixture_ids: list[str]
    ) -> list[dict[str, Any]]:
        assert fixture_ids == ["fixture-1"]
        return [{"fixture_id": "fixture-1", "canonical_market": "TOTALS"}]

    def future_market_observations(self) -> list[dict[str, Any]]:
        raise AssertionError("global observation query must not be used")

    def persist_frozen_analysis_checkpoint(self, **kwargs: Any) -> dict[str, str]:
        self.persisted.append(kwargs)
        return {
            "fixture_id": "fixture-1",
            "source_hash": "hash-1",
            "immutable_checkpoint_key": "immutable-1",
            "latest_checkpoint_key": "latest-1",
        }

    def frozen_analysis_source_signature(self, fixture_id: str) -> str | None:
        if not self.persisted:
            return None
        materialization = self.persisted[-1]["payload"].get("analysis_materialization", {})
        return cast(str | None, materialization.get("source_signature"))


def test_materializer_uses_fixture_scoped_observations(monkeypatch: Any) -> None:
    repository = _Repository()
    service = ReadModelService(repository=cast(Any, repository))

    def build(
        fixture_id: str,
        item: dict[str, Any],
    ) -> dict[str, Any]:
        assert fixture_id == "fixture-1"
        assert item["fixture"]["id"] == "fixture-1"
        assert service._observations_for_fixture(fixture_id) == [
            {"fixture_id": "fixture-1", "canonical_market": "TOTALS"}
        ]
        return {
            "fixture_id": fixture_id,
            "fair_market_estimate_snapshots": [{"estimate_id": "fme-1"}],
        }

    monkeypatch.setattr(service, "_analysis_card_from_provider_payload", build)

    result = service.materialize_frozen_analysis_cards(["fixture-1", "fixture-1"])

    assert result["status"] == "COMPLETED"
    assert result["fixture_count"] == 1
    assert result["materialized_count"] == 1
    assert result["provider_calls"] == 0
    assert repository.persisted[0]["fixture_id"] == "fixture-1"
    assert repository.persisted[0]["payload"]["analysis_card"][
        "fair_market_estimate_snapshots"
    ] == [{"estimate_id": "fme-1"}]


def test_offline_builder_primes_fixture_scope_before_reconstruction(monkeypatch: Any) -> None:
    repository = _Repository()
    service = ReadModelService(repository=cast(Any, repository))

    monkeypatch.setattr(
        service,
        "_analysis_card_in_request",
        lambda fixture_id: {
            "fixture_id": fixture_id,
            "observation_count": len(service._observations_for_fixture(fixture_id)),
        },
    )

    assert service.build_analysis_card_offline("fixture-1") == {
        "fixture_id": "fixture-1",
        "observation_count": 1,
    }


def test_reconcile_is_bounded_fixture_scoped_and_idempotent(monkeypatch: Any) -> None:
    repository = _Repository()
    service = ReadModelService(repository=cast(Any, repository))
    builds = 0

    def build(fixture_id: str, item: dict[str, Any]) -> dict[str, Any]:
        nonlocal builds
        builds += 1
        return {
            "fixture_id": fixture_id,
            "decision_tier": "NOT_READY",
            "data_status": "STALE",
            "current_odds": {"ou": {"line": "2.5"}},
            "fair_market_estimate_snapshots": [],
        }

    monkeypatch.setattr(service, "_analysis_card_from_provider_payload", build)

    first = service.reconcile_frozen_analysis_cards(["fixture-1"] * 12, max_fixtures=10)
    second = service.reconcile_frozen_analysis_cards(["fixture-1"], max_fixtures=10)

    assert first["fixture_count"] == 1
    assert first["materialized_count"] == 1
    assert first["provider_calls"] == 0
    assert second["materialized_count"] == 0
    assert second["unchanged_count"] == 1
    assert builds == 1


def test_worker_materializes_checkpoint_after_completed_refresh(monkeypatch: Any) -> None:
    worker = importlib.import_module("apps.worker.celery_app")
    audit = SimpleNamespace(
        task_id="task-1",
        key="key-1",
        status="COMPLETED",
        result={"blockers": [], "provider_calls": 3},
    )
    monkeypatch.setattr(worker, "provider_scheduler_enabled", lambda: True)
    monkeypatch.setattr(worker, "run_future_refresh_task", lambda **_kwargs: audit)

    class Materializer:
        def materialize_frozen_analysis_cards(self, fixture_ids: list[str]) -> dict[str, object]:
            assert fixture_ids == ["fixture-1"]
            return {
                "status": "COMPLETED",
                "materialized_count": 1,
                "provider_calls": 0,
            }

    repository_module = importlib.import_module("w2.api.repository")
    monkeypatch.setattr(repository_module, "ReadModelService", Materializer)

    result = worker.future_fixture_refresh.run(
        competition_id="brasileirao_serie_a",
        task_key="key-1",
        checkpoint_fixture_ids=["fixture-1", "fixture-1"],
    )

    assert result["status"] == "COMPLETED"
    assert result["result"]["analysis_materialization"] == {
        "status": "COMPLETED",
        "materialized_count": 1,
        "provider_calls": 0,
    }


def test_matchday_projection_preserves_materialized_analysis(monkeypatch: Any) -> None:
    repository = ReadModelRepository()
    monkeypatch.setattr(
        repository,
        "dashboard_latest_fixtures",
        lambda: [
            {
                "fixture_id": "fixture-1",
                "analysis_card": {
                    "fixture_id": "fixture-1",
                    "fair_market_estimate_snapshots": [{"estimate_id": "fme-1"}],
                },
            }
        ],
    )
    monkeypatch.setattr(repository, "stage10c_matchday_cards", lambda: [])

    rows = repository.matchday_cards()

    assert rows[0]["analysis_card"]["fair_market_estimate_snapshots"] == [{"estimate_id": "fme-1"}]
