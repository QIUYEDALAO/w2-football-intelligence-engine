from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from w2.api.frozen_analysis import (
    ANALYSIS_CARD_CANARY_SCHEMA,
    AnalysisCardCanaryMaterializer,
    FrozenAnalysisError,
    read_frozen_analysis_artifact,
    validate_frozen_analysis_payload,
    write_frozen_analysis_artifacts,
)
from w2.api.repository import ReadModelService
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.operations.observability import default_metric_registry


class ScopedRepository:
    def __init__(self, fixture_id: str = "1576804") -> None:
        self.fixture_id = fixture_id
        self.fixture = {
            "fixture": {
                "id": fixture_id,
                "date": "2026-07-19T12:00:00Z",
                "status": {"short": "NS"},
            },
            "league": {"id": "league", "name": "League"},
            "teams": {
                "home": {"id": "home", "name": "Home"},
                "away": {"id": "away", "name": "Away"},
            },
        }
        self.observations = [
            {
                "observation_id": "observation-1",
                "fixture_id": fixture_id,
                "canonical_market": "TOTALS",
                "captured_at": "2026-07-18T04:00:00Z",
                "selection": "Over",
                "line": "2.5",
                "decimal_odds": "1.91",
            }
        ]
        self.fixture_calls: list[str] = []
        self.observation_calls: list[list[str]] = []
        self.global_calls = 0

    def fixture_payload(self, fixture_id: str) -> dict[str, Any] | None:
        self.fixture_calls.append(fixture_id)
        return self.fixture if fixture_id == self.fixture_id else None

    def future_market_observations_for_fixtures(
        self,
        fixture_ids: list[str],
    ) -> list[dict[str, Any]]:
        self.observation_calls.append(fixture_ids)
        return [dict(row) for row in self.observations]

    def fixture_payloads(self) -> list[dict[str, Any]]:
        self.global_calls += 1
        raise AssertionError("global fixture reader called")

    def future_market_observations(self) -> list[dict[str, Any]]:
        self.global_calls += 1
        raise AssertionError("global observation reader called")


def _patch_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    def project(
        self: ReadModelService,
        fixture_id: str,
        *,
        evaluation_time: datetime | None = None,
        use_frozen_canary: bool = True,
    ) -> dict[str, Any]:
        assert evaluation_time is not None
        assert use_frozen_canary is False
        return {
            "fixture_id": fixture_id,
            "decision": "SKIP",
            "decision_tier": "NOT_READY",
            "pick": None,
            "evaluated_at": evaluation_time.astimezone(UTC).isoformat(),
        }

    monkeypatch.setattr(ReadModelService, "public_analysis_card_bounded", project)


def _engine():  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ReadModelCheckpointModel.__table__.create(engine)
    return engine


def test_same_inputs_produce_identical_bytes_and_hashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_projection(monkeypatch)
    repository = ScopedRepository()
    materializer = AnalysisCardCanaryMaterializer(repository)
    evaluated_at = datetime(2026, 7, 18, 5, 0, tzinfo=UTC)

    first = materializer.build("1576804", evaluated_at=evaluated_at)
    second = materializer.build("1576804", evaluated_at=evaluated_at)

    assert first.canonical_bytes == second.canonical_bytes
    assert first.source_hash == second.source_hash
    assert first.artifact_hash == second.artifact_hash
    assert first.payload["schema_version"] == ANALYSIS_CARD_CANARY_SCHEMA
    assert "created_at" not in first.payload
    assert "run_id" not in first.payload
    assert repository.global_calls == 0


def test_missing_or_conflicting_scoped_inputs_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_projection(monkeypatch)
    repository = ScopedRepository()
    repository.observations = []
    materializer = AnalysisCardCanaryMaterializer(repository)
    registry = default_metric_registry()
    error_key = ("w2_materializer_results_total", (("status", "ERROR"),))
    errors_before = registry.labelled_counters.get(error_key, 0)

    with pytest.raises(FrozenAnalysisError, match="observation input missing"):
        materializer.build("1576804", evaluated_at=datetime.now(UTC))

    repository.observations = [{"fixture_id": "other"}]
    with pytest.raises(FrozenAnalysisError, match="observation identity conflict"):
        materializer.build("1576804", evaluated_at=datetime.now(UTC))

    repository.fixture["fixture"]["id"] = "other"
    with pytest.raises(FrozenAnalysisError, match="fixture identity conflict"):
        materializer.build("1576804", evaluated_at=datetime.now(UTC))
    assert registry.labelled_counters[error_key] == errors_before + 3


def test_write_is_idempotent_and_reader_verifies_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_projection(monkeypatch)
    artifact = AnalysisCardCanaryMaterializer(ScopedRepository()).build(
        "1576804",
        evaluated_at=datetime(2026, 7, 18, 5, 0, tzinfo=UTC),
    )
    engine = _engine()
    registry = default_metric_registry()
    hit_key = ("w2_checkpoint_reads_total", (("status", "HIT"),))
    invalid_key = ("w2_checkpoint_reads_total", (("status", "INVALID"),))
    hits_before = registry.labelled_counters.get(hit_key, 0)
    invalid_before = registry.labelled_counters.get(invalid_key, 0)

    write_frozen_analysis_artifacts(engine, [artifact])
    write_frozen_analysis_artifacts(engine, [artifact])
    loaded = read_frozen_analysis_artifact(engine, "1576804")

    assert loaded is not None
    assert loaded.canonical_bytes == artifact.canonical_bytes
    assert registry.labelled_counters[hit_key] == hits_before + 1
    with Session(engine) as session:
        assert session.query(ReadModelCheckpointModel).count() == 1

    with Session(engine) as session:
        row = session.query(ReadModelCheckpointModel).one()
        row.payload = {**row.payload, "analysis_card": {"fixture_id": "1576804"}}
        session.commit()
    with pytest.raises(FrozenAnalysisError, match="artifact hash mismatch"):
        read_frozen_analysis_artifact(engine, "1576804")
    assert registry.labelled_counters[invalid_key] == invalid_before + 1


def test_old_schema_blocks_entire_atomic_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_projection(monkeypatch)
    first = AnalysisCardCanaryMaterializer(ScopedRepository("fixture-a")).build(
        "fixture-a",
        evaluated_at=datetime(2026, 7, 18, 5, 0, tzinfo=UTC),
    )
    second = AnalysisCardCanaryMaterializer(ScopedRepository("fixture-b")).build(
        "fixture-b",
        evaluated_at=datetime(2026, 7, 18, 5, 0, tzinfo=UTC),
    )
    engine = _engine()
    with Session(engine) as session:
        session.add(
            ReadModelCheckpointModel(
                checkpoint_key=second.checkpoint_key,
                source_hash="0" * 64,
                created_at=datetime.now(UTC),
                payload={"schema_version": "old"},
            )
        )
        session.commit()

    with pytest.raises(FrozenAnalysisError, match="schema incompatible"):
        write_frozen_analysis_artifacts(engine, [first, second])

    registry = default_metric_registry()
    miss_key = ("w2_checkpoint_reads_total", (("status", "MISS"),))
    misses_before = registry.labelled_counters.get(miss_key, 0)
    assert read_frozen_analysis_artifact(engine, "fixture-a") is None
    assert registry.labelled_counters[miss_key] == misses_before + 1


def test_payload_validation_rejects_fixture_identity_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_projection(monkeypatch)
    artifact = AnalysisCardCanaryMaterializer(ScopedRepository()).build(
        "1576804",
        evaluated_at=datetime(2026, 7, 18, 5, 0, tzinfo=UTC),
    )

    with pytest.raises(FrozenAnalysisError, match="fixture identity conflict"):
        validate_frozen_analysis_payload("other", artifact.payload)
