from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from w2.api.repository import ReadModelService, SystemDegradedError

API_ROOTS = (Path("src/w2/api"), Path("apps/api"))
FULL_EXECUTION_SURFACE = (*API_ROOTS, Path("scripts"), Path("infra"))
FORBIDDEN_API_PACKAGES = {
    "w2.ingestion",
    "w2.features",
    "w2.markets",
    "w2.pricing",
    "w2.strategy",
    "w2.simulation",
}
FORBIDDEN_PRODUCTION_FALLBACKS = {
    "prediction_locks.json",
    "result_events.json",
    "_uses_frozen_public_authority",
    "staging_seed_dashboard",
}
NON_PRODUCTION_FALLBACK_READERS = {
    Path("scripts/run_stage7i_observer.py"),
    Path("scripts/seed_staging_dashboard.py"),
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_api_imports_no_read_time_computation_packages() -> None:
    violations = sorted(
        f"{path}:{name}"
        for root in API_ROOTS
        for path in root.rglob("*.py")
        for name in _imports(path)
        if any(
            name == package or name.startswith(f"{package}.")
            for package in FORBIDDEN_API_PACKAGES
        )
    )
    assert violations == []


def test_full_execution_surface_has_no_removed_production_fallback_identity() -> None:
    # scripts/ and infra/ are intentionally part of this scan so a deployment
    # entrypoint cannot silently reintroduce the removed API fallback. The one
    # allowlist entries are audit/seed utilities and cannot serve API traffic.
    violations = sorted(
        f"{path}:{identity}"
        for root in FULL_EXECUTION_SURFACE
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".py", ".sh", ".yml", ".yaml"}
        and path not in NON_PRODUCTION_FALLBACK_READERS
        for identity in FORBIDDEN_PRODUCTION_FALLBACKS
        if identity in path.read_text(encoding="utf-8", errors="ignore")
    )
    assert violations == []


def test_predeploy_projection_smoke_uses_write_side_calculator() -> None:
    source = Path("scripts/run_predeploy_e2e_smoke.sh").read_text(encoding="utf-8")
    assert (
        "from w2.prematch.analysis_calculator import "
        "ReadModelRepository, ReadModelService"
    ) in source
    assert "from w2.api.repository import ReadModelRepository, ReadModelService" not in source


class ProjectionRepository:
    def __init__(self, *, projection: dict[str, Any] | None) -> None:
        self.projection = projection
        self.fixture = {
            "fixture_id": "fixture-1",
            "competition_id": "competition-1",
            "competition_name": "Competition",
            "kickoff_utc": "2026-07-25T12:00:00Z",
            "status": "NS",
            "home_team_id": "home-1",
            "home_team_name": "Home",
            "away_team_id": "away-1",
            "away_team_name": "Away",
        }

    def dashboard_latest_fixtures(self) -> list[dict[str, Any]]:
        return [self.fixture]

    def dashboard_fixture(self, fixture_id: str) -> dict[str, Any] | None:
        return self.fixture if fixture_id == "fixture-1" else None

    def analysis_card_projection(self, fixture_id: str) -> dict[str, Any] | None:
        return self.projection if fixture_id == "fixture-1" else None

    def release_counts(self) -> dict[str, int]:
        return {
            "read_model_fixture_count": 1,
            "matchday_card_count": 1,
            "future_fixture_count": 1,
            "result_event_count": 0,
        }


def test_analysis_endpoint_returns_projection_metadata_without_recomputation() -> None:
    projected = {
        "fixture_id": "fixture-1",
        "decision_tier": "NOT_READY",
        "data_status": "BLOCKED",
        "lifecycle_status": "DRAFT",
        "current_odds": {},
        "market_probabilities": {},
        "recommendation_decision_v3": {
            "schema_version": "w2.recommendation_decision.v3",
            "outcome": "NO_EDGE",
            "selected_candidate": None,
        },
        "read_model_projection": {
            "checkpoint_key": "analysis-card:shadow:v1:fixture-1",
            "projection_version": "w2.prematch-read-model-projection.v1",
            "projection_hash": "projection-hash",
            "source_event_type": "ODDS_CHANGED",
            "source_event_at": "2026-07-24T01:00:00Z",
            "last_projected_at": "2026-07-24T01:00:01Z",
        },
    }
    service = ReadModelService(repository=ProjectionRepository(projection=projected))  # type: ignore[arg-type]

    card = service.public_analysis_card_bounded("fixture-1")

    assert card == projected
    assert card["read_model_projection"]["projection_hash"] == "projection-hash"
    assert card["read_model_projection"]["source_event_type"] == "ODDS_CHANGED"


def test_missing_projection_is_explicit_system_degraded_not_empty() -> None:
    service = ReadModelService(repository=ProjectionRepository(projection=None))  # type: ignore[arg-type]

    card = service.public_analysis_card_bounded("fixture-1")

    assert card is not None
    assert card["recommendation_decision_v3"]["outcome"] == "SYSTEM_DEGRADED"
    assert card["decision_tier"] == "NOT_READY"
    assert card["data_status"] == "BLOCKED"
    assert card["current_odds"] == {}


class FailedProjectionRepository(ProjectionRepository):
    def dashboard_fixture(self, fixture_id: str) -> dict[str, Any] | None:
        raise SystemDegradedError("READ_MODEL_CHECKPOINT_QUERY_FAILED")


def test_database_failure_propagates_system_degraded() -> None:
    service = ReadModelService(repository=FailedProjectionRepository(projection=None))  # type: ignore[arg-type]

    try:
        service.public_analysis_card_bounded("fixture-1")
    except SystemDegradedError as exc:
        assert exc.code == "SYSTEM_DEGRADED"
        assert str(exc) == "READ_MODEL_CHECKPOINT_QUERY_FAILED"
    else:
        raise AssertionError("database failure was silently converted to empty data")


def test_projection_read_is_read_only_across_twenty_calls() -> None:
    projection = {
        "fixture_id": "fixture-1",
        "decision_tier": "NOT_READY",
        "data_status": "BLOCKED",
        "lifecycle_status": "DRAFT",
        "recommendation_decision_v3": {
            "schema_version": "w2.recommendation_decision.v3",
            "outcome": "NO_EDGE",
            "selected_candidate": None,
        },
        "read_model_projection": {
            "checkpoint_key": "analysis-card:shadow:v1:fixture-1",
            "projection_version": "w2.prematch-read-model-projection.v1",
            "projection_hash": "stable",
            "source_event_type": "FIXTURE_CHANGED",
            "source_event_at": datetime(2026, 7, 24, tzinfo=UTC).isoformat(),
            "last_projected_at": datetime(2026, 7, 24, 0, 0, 1, tzinfo=UTC).isoformat(),
        },
    }
    repository = ProjectionRepository(projection=projection)
    service = ReadModelService(repository=repository)  # type: ignore[arg-type]

    hashes = [
        service.public_analysis_card_bounded("fixture-1")["read_model_projection"][
            "projection_hash"
        ]
        for _ in range(20)
    ]

    assert hashes == ["stable"] * 20
