from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any, cast

from apps.api.main import app
from fastapi.testclient import TestClient

from w2.api import repository as api_repository
from w2.api import routers
from w2.api.repository import ReadModelService


class BoundedObservationRepository:
    def __init__(
        self,
        fixture_ids: list[str],
        *,
        scoped_rows: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self.fixture_ids = fixture_ids
        self.scoped_rows = scoped_rows or {
            fixture_id: [_observation(fixture_id)] for fixture_id in fixture_ids
        }
        self.global_calls = 0
        self.latest_calls = 0
        self.scoped_calls: list[list[str]] = []
        self.scoped_error: Exception | None = None
        self.barrier: Barrier | None = None
        self.unrelated_rows: list[dict[str, Any]] = []

    def matchday_cards(self) -> list[dict[str, Any]]:
        return []

    def dashboard_fixture(self, fixture_id: str) -> dict[str, Any] | None:
        return None

    def fixture_payloads(self) -> list[dict[str, Any]]:
        return [_fixture_payload(fixture_id) for fixture_id in self.fixture_ids]

    def future_market_observations(self) -> list[dict[str, Any]]:
        self.global_calls += 1
        return self.latest_market_observations()

    def latest_market_observations(self) -> list[dict[str, Any]]:
        self.latest_calls += 1
        raise AssertionError("global observation reader must not be called")

    def future_market_observations_for_fixtures(
        self,
        fixture_ids: list[str],
    ) -> list[dict[str, Any]]:
        self.scoped_calls.append(list(fixture_ids))
        if self.barrier is not None:
            self.barrier.wait(timeout=2)
        if self.scoped_error is not None:
            raise self.scoped_error
        return [dict(row) for fixture_id in fixture_ids for row in self.scoped_rows[fixture_id]]


def _fixture_payload(fixture_id: str) -> dict[str, Any]:
    return {
        "fixture": {
            "id": fixture_id,
            "date": "2026-07-19T12:00:00Z",
            "status": {"short": "NS"},
        },
        "league": {"id": "test", "name": "Test League"},
        "teams": {
            "home": {"id": f"home-{fixture_id}", "name": f"Home {fixture_id}"},
            "away": {"id": f"away-{fixture_id}", "name": f"Away {fixture_id}"},
        },
    }


def _observation(fixture_id: str) -> dict[str, Any]:
    return {
        "observation_id": f"observation-{fixture_id}",
        "fixture_id": fixture_id,
        "canonical_market": "TOTALS",
    }


def _bounded_card_builder(
    service: ReadModelService,
    fixture_id: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    observations = service._observations_for_fixture(fixture_id)
    return {
        "fixture_id": fixture_id,
        "decision": "PICK",
        "markets": [{"market": "TOTALS", "decision": "PICK"}],
        "candidate": False,
        "formal_recommendation": False,
        "lock_eligible": False,
        "data_readiness": {"market_observations": len(observations)},
        "quote_identity_audit": {
            "observed_fixture_ids": sorted(
                {str(row.get("fixture_id") or "") for row in observations}
            ),
            "observation_ids": sorted(
                {str(row.get("observation_id") or "") for row in observations}
            ),
        },
    }


def _patch_card_builder(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        api_repository.ReadModelService,
        "_analysis_card_from_provider_payload",
        _bounded_card_builder,
    )


def test_public_analysis_card_uses_fixture_scoped_observation_reader(
    monkeypatch: Any,
) -> None:
    _patch_card_builder(monkeypatch)
    repository = BoundedObservationRepository(["target"])
    monkeypatch.setattr(
        routers,
        "service",
        ReadModelService(repository=cast(Any, repository)),
    )

    response = TestClient(app).get("/v1/fixtures/target/analysis-card")

    assert response.status_code == 200
    assert repository.scoped_calls == [["target"]]
    assert repository.global_calls == 0
    assert response.json()["card"]["quote_identity_audit"]["observed_fixture_ids"] == [
        "target"
    ]
    assert response.json()["card"]["decision_tier"] == "NOT_READY"
    assert response.json()["card"]["decision"] == "SKIP"
    assert response.json()["card"]["pick"] is None
    assert response.json()["card"]["recommendation_id"] is None
    assert response.json()["card"]["lock_eligible"] is False
    assert response.json()["card"]["outcome_tracked"] is False


def test_public_analysis_card_never_calls_latest_market_observations(
    monkeypatch: Any,
) -> None:
    _patch_card_builder(monkeypatch)
    repository = BoundedObservationRepository(["target"])

    card = ReadModelService(repository=cast(Any, repository)).public_analysis_card_bounded(
        "target"
    )

    assert card is not None
    assert repository.latest_calls == 0
    assert repository.global_calls == 0


def test_fixture_scoped_reader_rejects_cross_fixture_rows(monkeypatch: Any) -> None:
    _patch_card_builder(monkeypatch)
    repository = BoundedObservationRepository(
        ["target"],
        scoped_rows={"target": [_observation("other")]},
    )

    card = ReadModelService(repository=cast(Any, repository)).public_analysis_card_bounded(
        "target"
    )

    assert card is not None
    assert card["bounded_read"] == {
        "status": "BLOCKED",
        "blockers": ["FIXTURE_SCOPED_OBSERVATION_CROSS_FIXTURE_ROWS"],
    }
    assert card["decision"] == "SKIP"
    assert card["candidate"] is False
    assert card["formal_recommendation"] is False
    assert card["lock_eligible"] is False
    assert all(market["decision"] == "SKIP" for market in card["markets"])
    assert card["quote_identity_audit"]["ah"]["identity_status"] == "INCOMPLETE"
    assert repository.global_calls == 0


def test_fixture_scoped_reader_failure_does_not_fallback_global(monkeypatch: Any) -> None:
    _patch_card_builder(monkeypatch)
    repository = BoundedObservationRepository(["target"])
    repository.scoped_error = RuntimeError("scoped reader failed")

    card = ReadModelService(repository=cast(Any, repository)).public_analysis_card_bounded(
        "target"
    )

    assert card is not None
    assert card["bounded_read"]["blockers"] == ["FIXTURE_SCOPED_OBSERVATION_READ_FAILED"]
    assert card["decision"] == "SKIP"
    assert repository.global_calls == 0
    assert repository.latest_calls == 0


def test_missing_fixture_scoped_reader_returns_blocked_card(monkeypatch: Any) -> None:
    _patch_card_builder(monkeypatch)

    class RepositoryWithoutScopedReader:
        def matchday_cards(self) -> list[dict[str, Any]]:
            return []

        def dashboard_fixture(self, fixture_id: str) -> dict[str, Any] | None:
            return None

        def fixture_payloads(self) -> list[dict[str, Any]]:
            return [_fixture_payload("target")]

        def future_market_observations(self) -> list[dict[str, Any]]:
            raise AssertionError("global observation reader must not be called")

    card = ReadModelService(
        repository=cast(Any, RepositoryWithoutScopedReader())
    ).public_analysis_card_bounded("target")

    assert card is not None
    assert card["bounded_read"]["blockers"] == [
        "FIXTURE_SCOPED_OBSERVATION_READER_UNAVAILABLE"
    ]
    assert card["decision"] == "SKIP"
    assert card["lock_eligible"] is False


def test_concurrent_analysis_card_requests_do_not_share_fixture_cache(
    monkeypatch: Any,
) -> None:
    _patch_card_builder(monkeypatch)
    repository = BoundedObservationRepository(["fixture-a", "fixture-b"])
    repository.barrier = Barrier(2)
    service = ReadModelService(repository=cast(Any, repository))

    with ThreadPoolExecutor(max_workers=2) as executor:
        cards = list(
            executor.map(service.public_analysis_card_bounded, ["fixture-a", "fixture-b"])
        )

    assert all(card is not None for card in cards)
    assert [card["quote_identity_audit"]["observed_fixture_ids"] for card in cards if card] == [
        ["fixture-a"],
        ["fixture-b"],
    ]
    assert service._future_market_observations_cache is None
    assert service._observations_by_fixture_cache is None
    assert repository.global_calls == 0


def test_large_unrelated_observation_population_does_not_affect_target_read(
    monkeypatch: Any,
) -> None:
    _patch_card_builder(monkeypatch)
    repository = BoundedObservationRepository(["target"])
    repository.unrelated_rows = [
        _observation(f"unrelated-{index}") for index in range(20_000)
    ]

    card = ReadModelService(repository=cast(Any, repository)).public_analysis_card_bounded(
        "target"
    )

    assert card is not None
    assert card["data_readiness"]["market_observations"] == 1
    assert repository.scoped_calls == [["target"]]
    assert repository.global_calls == 0
    assert repository.latest_calls == 0


def test_public_bounded_read_projects_canonical_no_pick_contract(monkeypatch: Any) -> None:
    _patch_card_builder(monkeypatch)
    repository = BoundedObservationRepository(["target"])
    repository.future_market_observations = lambda: [_observation("target")]  # type: ignore[method-assign]

    legacy_card = ReadModelService(repository=cast(Any, repository)).analysis_card("target")
    bounded_card = ReadModelService(
        repository=cast(Any, repository)
    ).public_analysis_card_bounded("target")

    assert legacy_card is not None
    assert bounded_card is not None
    assert legacy_card["decision"] == "PICK"
    assert bounded_card["decision_tier"] == "NOT_READY"
    assert bounded_card["decision"] == "SKIP"
    assert bounded_card["pick"] is None
    assert bounded_card["recommendation_id"] is None
    assert bounded_card["lock_eligible"] is False
    assert bounded_card["outcome_tracked"] is False
    assert bounded_card["current_odds"] == {}
    assert all(market["decision"] != "PICK" for market in bounded_card["markets"])
