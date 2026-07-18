from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast

import pytest
from apps.api.main import app
from fastapi.testclient import TestClient

from w2.api import routers
from w2.api.frozen_analysis import (
    ANALYSIS_CARD_CANARY_SCHEMA,
    FrozenAnalysisArtifact,
    FrozenAnalysisError,
    analysis_card_canary_key,
    canonical_json_bytes,
    canonical_sha256,
    validate_frozen_analysis_payload,
)
from w2.api.repository import ReadModelService
from w2.dashboard.day_view import build_dashboard_day_view


def _artifact(fixture_id: str = "1576804") -> FrozenAnalysisArtifact:
    card = {
        "fixture_id": fixture_id,
        "decision": "SKIP",
        "decision_tier": "NOT_READY",
        "data_status": "BLOCKED",
        "pick": None,
        "current_odds": {},
        "candidate": False,
        "formal_recommendation": False,
        "lock_eligible": False,
        "outcome_tracked": False,
        "quote_identity_audit": {
            "ah": {
                "identity_status": "INCOMPLETE",
                "captured_at": "2026-07-18T04:00:00Z",
            },
            "ou": {
                "identity_status": "COMPLETE",
                "captured_at": "2026-07-18T04:00:00Z",
            },
        },
    }
    manifest = {
        "evaluated_at": "2026-07-18T05:00:00Z",
        "fixture_payload_sha256": "1" * 64,
        "observation_count": 2,
        "observation_sha256": ["2" * 64, "3" * 64],
    }
    body = {
        "schema_version": ANALYSIS_CARD_CANARY_SCHEMA,
        "checkpoint_namespace": "public",
        "fixture_identity": {
            "fixture_id": fixture_id,
            "competition_id": "league",
            "kickoff_utc": "2026-07-19T12:00:00Z",
            "home_team_id": "home",
            "away_team_id": "away",
        },
        "input_manifest": manifest,
        "analysis_card": card,
    }
    payload = {**body, "artifact_hash": canonical_sha256(body)}
    return validate_frozen_analysis_payload(fixture_id, payload)


class FrozenRepository:
    def __init__(self, artifact: FrozenAnalysisArtifact | None) -> None:
        self.artifact = artifact
        self.reads: list[str] = []
        self.forbidden_calls = 0

    def analysis_card_canary_artifact(
        self,
        fixture_id: str,
    ) -> FrozenAnalysisArtifact | None:
        self.reads.append(fixture_id)
        return self.artifact

    def fixture_payload(self, fixture_id: str) -> dict[str, Any] | None:
        self.forbidden_calls += 1
        raise AssertionError("fixture source must not be read by frozen canary")

    def future_market_observations_for_fixtures(
        self,
        fixture_ids: list[str],
    ) -> list[dict[str, Any]]:
        self.forbidden_calls += 1
        raise AssertionError("observations must not be read by frozen canary")

    def future_market_observations(self) -> list[dict[str, Any]]:
        self.forbidden_calls += 1
        raise AssertionError("global observations must not be read")

    def provider_request(self, *_args: Any, **_kwargs: Any) -> Any:
        self.forbidden_calls += 1
        raise AssertionError("provider must not be called")

    def model_request(self, *_args: Any, **_kwargs: Any) -> Any:
        self.forbidden_calls += 1
        raise AssertionError("model must not be called")


def test_canary_reads_only_verified_frozen_artifact() -> None:
    artifact = _artifact()
    repository = FrozenRepository(artifact)

    card = ReadModelService(repository=cast(Any, repository)).public_analysis_card_bounded(
        "1576804"
    )

    assert card is not None
    assert card["decision"] == "SKIP"
    assert card["decision_tier"] == "NOT_READY"
    assert card["pick"] is None
    assert card["quote_identity_audit"] == artifact.payload["analysis_card"]["quote_identity_audit"]
    assert card["frozen_artifact_provenance"] == {
        "status": "VERIFIED",
        "schema_version": ANALYSIS_CARD_CANARY_SCHEMA,
        "checkpoint_namespace": "public",
        "checkpoint_key": analysis_card_canary_key("1576804"),
        "source_hash": artifact.source_hash,
        "artifact_hash": artifact.artifact_hash,
        "fixture_identity": artifact.payload["fixture_identity"],
        "input_manifest": artifact.payload["input_manifest"],
    }
    assert repository.reads == ["1576804"]
    assert repository.forbidden_calls == 0


def test_canary_response_is_stable_for_sequential_and_concurrent_reads() -> None:
    repository = FrozenRepository(_artifact())
    service = ReadModelService(repository=cast(Any, repository))

    sequential = [service.public_analysis_card_bounded("1576804") for _ in range(5)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        concurrent = list(executor.map(service.public_analysis_card_bounded, ["1576804"] * 8))
    encoded = [canonical_json_bytes(card) for card in [*sequential, *concurrent]]

    assert len(set(encoded)) == 1
    assert repository.forbidden_calls == 0


def test_missing_canary_fails_closed_without_legacy_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FrozenRepository(None)
    monkeypatch.setattr(
        ReadModelService,
        "analysis_card",
        lambda *_args, **_kwargs: pytest.fail("legacy builder called"),
    )

    card = ReadModelService(repository=cast(Any, repository)).public_analysis_card_bounded(
        "1576804"
    )

    assert card is not None
    assert card["decision_tier"] == "NOT_READY"
    assert card["decision"] == "SKIP"
    assert card["pick"] is None
    assert card["current_odds"] == {}
    assert card["lock_eligible"] is False
    assert card["outcome_tracked"] is False
    assert card["frozen_artifact_provenance"] == {
        "status": "BLOCKED",
        "blockers": ["FROZEN_ARTIFACT_MISSING"],
    }
    assert repository.forbidden_calls == 0


@pytest.mark.parametrize(
    ("message", "blocker"),
    [
        ("checkpoint schema incompatible", "FROZEN_ARTIFACT_SCHEMA_INCOMPATIBLE"),
        ("checkpoint fixture identity conflict", "FROZEN_ARTIFACT_IDENTITY_CONFLICT"),
        ("checkpoint artifact hash mismatch", "FROZEN_ARTIFACT_HASH_INVALID"),
    ],
)
def test_invalid_canary_artifact_maps_to_structured_not_ready(
    message: str,
    blocker: str,
) -> None:
    class InvalidRepository(FrozenRepository):
        def analysis_card_canary_artifact(self, fixture_id: str) -> FrozenAnalysisArtifact | None:
            raise FrozenAnalysisError(message)

    card = ReadModelService(
        repository=cast(Any, InvalidRepository(None))
    ).public_analysis_card_bounded("1576804")

    assert card is not None
    assert card["decision_tier"] == "NOT_READY"
    assert card["reason_code"] == blocker
    assert card["pick"] is None
    assert card["frozen_artifact_provenance"]["blockers"] == [blocker]


def test_public_route_exposes_frozen_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    artifact = _artifact()
    repository = FrozenRepository(artifact)
    monkeypatch.setattr(
        routers,
        "service",
        ReadModelService(repository=cast(Any, repository)),
    )

    response = TestClient(app).get("/v1/fixtures/1576804/analysis-card")

    assert response.status_code == 200
    payload = response.json()
    assert payload["fixture_id"] == "1576804"
    assert payload["card"]["frozen_artifact_provenance"]["artifact_hash"] == (
        artifact.artifact_hash
    )
    assert json.dumps(payload["card"])


def test_non_canary_fixture_also_fails_closed_without_frozen_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FrozenRepository(None)
    monkeypatch.setattr(
        ReadModelService,
        "analysis_card",
        lambda *_args, **_kwargs: pytest.fail("legacy builder called"),
    )

    card = ReadModelService(repository=cast(Any, repository)).public_analysis_card_bounded(
        "1523206"
    )

    assert card is not None
    assert card["decision_tier"] == "NOT_READY"
    assert card["pick"] is None
    assert card["frozen_artifact_provenance"]["blockers"] == [
        "FROZEN_ARTIFACT_MISSING"
    ]


def test_fixture_dashboard_and_day_view_share_frozen_authority() -> None:
    artifact = _artifact()

    class PublicRepository(FrozenRepository):
        def dashboard_fixture(self, fixture_id: str) -> dict[str, Any] | None:
            if fixture_id != "1576804":
                return None
            return {
                "fixture_id": fixture_id,
                "competition_id": "league",
                "competition_name": "League",
                "kickoff_utc": "2026-07-19T12:00:00Z",
                "status": "NS",
                "home_team_id": "home",
                "home_team_name": "Home",
                "away_team_id": "away",
                "away_team_name": "Away",
                "market_coverage": {},
            }

    repository = PublicRepository(artifact)
    service = ReadModelService(repository=cast(Any, repository))
    analysis = service.public_analysis_card_bounded("1576804")
    detail = service.fixture("1576804", "UTC")
    dashboard_card = service._dashboard_card_from_matchday(
        {
            "fixture_id": "1576804",
            "kickoff_utc": "2026-07-19T12:00:00Z",
            "competition_id": "league",
            "competition_name": "League",
            "home_team_name": "Home",
            "away_team_name": "Away",
            "status": "NS",
        }
    )
    day_view = build_dashboard_day_view(
        {
            "generated_at": "2026-07-18T05:00:00Z",
            "date": "2026-07-19",
            "selected_football_day": "2026-07-19",
            "timezone": "Asia/Shanghai",
            "window": "today",
            "version": {},
            "all": [dashboard_card],
        },
        environment="staging",
    )

    assert analysis is not None
    assert detail is not None
    expected_hash = artifact.artifact_hash
    assert analysis["frozen_artifact_provenance"]["artifact_hash"] == expected_hash
    assert detail["analysis_card"]["frozen_artifact_provenance"]["artifact_hash"] == (
        expected_hash
    )
    assert dashboard_card["artifact_hash"] == expected_hash
    assert day_view["cards"][0]["artifact_hash"] == expected_hash
    for card in (analysis, detail["analysis_card"], dashboard_card, day_view["cards"][0]):
        assert card["decision_tier"] == "NOT_READY"
        assert card["pick"] is None
        assert card["lock_eligible"] is False
        assert card["quote_identity_audit"] == analysis["quote_identity_audit"]
    assert repository.forbidden_calls == 0
