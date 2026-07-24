from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session

from w2.api.repository import ReadModelService
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.infrastructure.persistence.dynamic_prematch_models import (
    DynamicPrematchEvaluationModel,
    DynamicPrematchSupersessionModel,
)
from w2.operations.observability import default_metric_registry
from w2.prematch.read_model_projection import (
    ANALYSIS_CARD_CANARY_PREFIX,
    ANALYSIS_CARD_CANARY_SCHEMA,
    ANALYSIS_CARD_SHADOW_PREFIX,
    AnalysisCardCanaryMaterializer,
    FrozenAnalysisError,
    ProjectionSourceEvent,
    canonical_sha256,
    read_frozen_analysis_artifact,
    read_shadow_analysis_artifact,
    validate_frozen_analysis_payload,
    write_frozen_analysis_artifacts,
)
from w2.prematch.repository import DynamicPrematchRepository


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


def _patch_ready_projection(monkeypatch: pytest.MonkeyPatch) -> None:
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
            "decision_tier": "ANALYSIS_ONLY",
            "pick": None,
            "evaluated_at": evaluation_time.astimezone(UTC).isoformat(),
            "market_candidates": {
                "ou": {
                    "market": "TOTALS",
                    "selection": "OVER",
                    "line": "2.5",
                    "analysis_evidence": {
                        "side_evidence": {
                            "OVER": {
                                "model_probability": {
                                    "status": "READY",
                                    "effective_probability": 0.58,
                                    "expected_value": 0.08,
                                    "ev_se": 0.01,
                                },
                                "comparison": {},
                            }
                        },
                        "quote_identity": {
                            "identity_status": "COMPLETE",
                            "freshness_status": "COMPLETE",
                            "quotes": {
                                "over": {
                                    "line": "2.5",
                                    "bookmaker_id": "book-1",
                                    "capture_id": "capture-1",
                                    "captured_at": "2026-07-18T04:00:00Z",
                                    "decimal_odds": "1.91",
                                }
                            },
                        },
                        "market_probability": {"devig": {"OVER": 0.52, "UNDER": 0.48}},
                    },
                }
            },
        }

    monkeypatch.setattr(ReadModelService, "public_analysis_card_bounded", project)


def _engine(*, dynamic: bool = False):  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ReadModelCheckpointModel.__table__.create(engine)
    if dynamic:
        DynamicPrematchEvaluationModel.__table__.create(engine)
        DynamicPrematchSupersessionModel.__table__.create(engine)
    return engine


def _calculate_projection(
    repository: Any,
    fixture_id: str,
    evaluated_at: datetime,
) -> dict[str, Any] | None:
    return ReadModelService(repository=repository).public_analysis_card_bounded(
        fixture_id,
        evaluation_time=evaluated_at,
        use_frozen_canary=False,
    )


def _materializer(
    repository: ScopedRepository,
    *,
    clock: Any | None = None,
) -> AnalysisCardCanaryMaterializer:
    return AnalysisCardCanaryMaterializer(
        repository,
        calculate_analysis_card=_calculate_projection,
        clock=clock,
    )


def _event(event_type: str = "ODDS_CHANGED") -> ProjectionSourceEvent:
    return ProjectionSourceEvent.create(
        fixture_id="1576804",
        event_type=event_type,
        event_id=f"{event_type.lower()}:capture-1",
        event_at=datetime(2026, 7, 18, 5, 0, tzinfo=UTC),
        payload={"capture_id": "capture-1"},
    )


def test_same_inputs_produce_identical_bytes_and_hashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_projection(monkeypatch)
    repository = ScopedRepository()
    materializer = _materializer(repository, clock=lambda: evaluated_at)
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
    materializer = _materializer(repository)
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
    artifact = _materializer(ScopedRepository()).build(
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
    assert registry.gauges["w2_checkpoint_lag_seconds"] >= 0
    assert registry.labelled_counters[hit_key] == hits_before + 1
    with Session(engine) as session:
        assert session.query(ReadModelCheckpointModel).count() == 1

    with Session(engine) as session:
        row = session.query(ReadModelCheckpointModel).one()
        row.payload = {**row.payload, "analysis_card": {"fixture_id": "1576804"}}
        session.commit()
    with pytest.raises(FrozenAnalysisError, match="projection hash mismatch"):
        read_frozen_analysis_artifact(engine, "1576804")
    assert registry.labelled_counters[invalid_key] == invalid_before + 1


def test_old_schema_blocks_entire_atomic_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_projection(monkeypatch)
    first = _materializer(ScopedRepository("fixture-a")).build(
        "fixture-a",
        evaluated_at=datetime(2026, 7, 18, 5, 0, tzinfo=UTC),
    )
    second = _materializer(ScopedRepository("fixture-b")).build(
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


def test_evidence_missing_checkpoint_is_replaced_by_verified_materialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_projection(monkeypatch)
    artifact = _materializer(ScopedRepository()).build(
        "1576804",
        evaluated_at=datetime(2026, 7, 18, 5, 0, tzinfo=UTC),
    )
    old_payload = dict(artifact.payload)
    old_body = {key: value for key, value in old_payload.items() if key != "artifact_hash"}
    old_manifest = dict(old_body["input_manifest"])
    old_manifest.pop("analysis_evidence_sha256")
    old_body["input_manifest"] = old_manifest
    old_payload = {**old_body, "artifact_hash": canonical_sha256(old_body)}
    engine = _engine()
    with Session(engine) as session:
        session.add(
            ReadModelCheckpointModel(
                checkpoint_key=artifact.checkpoint_key,
                source_hash="0" * 64,
                created_at=datetime.now(UTC),
                payload=old_payload,
            )
        )
        session.commit()

    write_frozen_analysis_artifacts(engine, [artifact])
    assert read_frozen_analysis_artifact(engine, "1576804") is not None


def test_payload_validation_rejects_fixture_identity_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_projection(monkeypatch)
    artifact = _materializer(ScopedRepository()).build(
        "1576804",
        evaluated_at=datetime(2026, 7, 18, 5, 0, tzinfo=UTC),
    )

    with pytest.raises(FrozenAnalysisError, match="fixture identity conflict"):
        validate_frozen_analysis_payload("other", artifact.payload)


def test_public_projection_preserves_existing_time_bound_hash_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_projection(monkeypatch)
    artifact = _materializer(ScopedRepository()).build(
        "1576804",
        evaluated_at=datetime(2026, 7, 18, 5, 0, tzinfo=UTC),
    )
    projection_body = {
        key: value
        for key, value in artifact.payload.items()
        if key not in {"projection_hash", "artifact_hash"}
    }

    assert artifact.payload["checkpoint_namespace"] == "public"
    assert artifact.payload["projection_hash"] == canonical_sha256(projection_body)
    validated = validate_frozen_analysis_payload("1576804", artifact.payload)
    assert validated.payload["projection_hash"] == artifact.payload["projection_hash"]
    assert validated.artifact_hash == artifact.artifact_hash


@pytest.mark.parametrize(
    "event_type",
    ["ODDS_CHANGED", "LINEUP_CHANGED", "FIXTURE_CHANGED"],
)
def test_event_projection_records_source_and_matches_current_read_hash(
    monkeypatch: pytest.MonkeyPatch,
    event_type: str,
) -> None:
    _patch_ready_projection(monkeypatch)
    event = _event(event_type)

    first = _materializer(ScopedRepository()).build(
        "1576804",
        evaluated_at=event.event_at,
        source_event=event,
    )
    second = _materializer(ScopedRepository()).build(
        "1576804",
        evaluated_at=event.event_at,
        source_event=event,
    )

    assert first.payload["source_event_type"] == event_type
    assert first.payload["source_event_id"] == event.event_id
    assert first.payload["source_event_hash"] == event.event_hash
    assert first.checkpoint_key == f"{ANALYSIS_CARD_SHADOW_PREFIX}1576804"
    assert first.payload["source_evaluation_id"]
    assert first.payload["source_evaluation_hash"]
    assert first.payload["projection_hash"] == second.payload["projection_hash"]
    assert first.payload["shadow_reconciliation"] == {
        "read_time_hash": canonical_sha256(first.payload["analysis_card"]),
        "projected_hash": canonical_sha256(first.payload["analysis_card"]),
        "match": True,
        "differences": [],
    }


def test_event_projection_writes_only_shadow_and_active_reader_remains_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ready_projection(monkeypatch)
    event = _event()
    artifact = _materializer(ScopedRepository()).build(
        "1576804",
        evaluated_at=event.event_at,
        source_event=event,
    )
    engine = _engine(dynamic=True)

    write_frozen_analysis_artifacts(engine, [artifact])

    assert artifact.checkpoint_key == f"{ANALYSIS_CARD_SHADOW_PREFIX}1576804"
    assert read_shadow_analysis_artifact(engine, "1576804") is not None
    assert read_frozen_analysis_artifact(engine, "1576804") is None
    with Session(engine) as session:
        keys = list(session.scalars(select(ReadModelCheckpointModel.checkpoint_key)))
    assert keys == [f"{ANALYSIS_CARD_SHADOW_PREFIX}1576804"]
    assert all(not key.startswith(ANALYSIS_CARD_CANARY_PREFIX) for key in keys)


def test_projection_time_is_completion_time_and_business_hash_ignores_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ready_projection(monkeypatch)
    event = _event()
    first_completed = datetime(2026, 7, 18, 5, 0, 3, tzinfo=UTC)
    second_completed = datetime(2026, 7, 18, 5, 0, 9, tzinfo=UTC)

    first = _materializer(ScopedRepository(), clock=lambda: first_completed).build(
        "1576804",
        evaluated_at=event.event_at,
        source_event=event,
    )
    second = _materializer(ScopedRepository(), clock=lambda: second_completed).build(
        "1576804",
        evaluated_at=event.event_at,
        source_event=event,
    )

    assert first.payload["source_event_at"] == "2026-07-18T05:00:00Z"
    assert first.payload["last_projected_at"] == "2026-07-18T05:00:03Z"
    assert second.payload["last_projected_at"] == "2026-07-18T05:00:09Z"
    assert first.payload["projection_hash"] == second.payload["projection_hash"]
    assert first.payload["artifact_hash"] != second.payload["artifact_hash"]

    engine = _engine(dynamic=True)
    write_frozen_analysis_artifacts(engine, [first])
    write_frozen_analysis_artifacts(engine, [second])
    with Session(engine) as session:
        assert session.query(DynamicPrematchEvaluationModel).count() == 1
        assert session.query(ReadModelCheckpointModel).count() == 1
        stored = session.query(ReadModelCheckpointModel).one()
        assert stored.payload["last_projected_at"] == "2026-07-18T05:00:03Z"


def test_shadow_reconciliation_reports_real_difference_fields() -> None:
    calls = 0

    def calculate(
        _repository: Any,
        fixture_id: str,
        evaluated_at: datetime,
    ) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {
            "fixture_id": fixture_id,
            "evaluated_at": evaluated_at.isoformat(),
            "decision": "SKIP" if calls == 1 else "ANALYSIS_ONLY",
        }

    artifact = AnalysisCardCanaryMaterializer(
        ScopedRepository(),
        calculate_analysis_card=calculate,
    ).build("1576804", evaluated_at=_event().event_at)

    assert artifact.payload["shadow_reconciliation"]["match"] is False
    assert artifact.payload["shadow_reconciliation"]["differences"] == ["decision"]
    assert (
        artifact.payload["shadow_reconciliation"]["read_time_hash"]
        != artifact.payload["shadow_reconciliation"]["projected_hash"]
    )


def test_event_projection_write_is_idempotent_for_evaluation_and_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ready_projection(monkeypatch)
    event = _event()
    artifact = _materializer(ScopedRepository()).build(
        "1576804",
        evaluated_at=event.event_at,
        source_event=event,
    )
    engine = _engine(dynamic=True)

    write_frozen_analysis_artifacts(engine, [artifact])
    write_frozen_analysis_artifacts(engine, [artifact])

    with Session(engine) as session:
        assert session.query(DynamicPrematchEvaluationModel).count() == 1
        assert session.query(ReadModelCheckpointModel).count() == 1
        checkpoint = session.query(ReadModelCheckpointModel).one()
        assert checkpoint.source_hash == artifact.source_hash
        assert checkpoint.payload["projection_hash"] == artifact.payload["projection_hash"]


def test_projection_failure_after_evaluation_is_repairable_without_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ready_projection(monkeypatch)
    event = _event()
    artifact = _materializer(ScopedRepository()).build(
        "1576804",
        evaluated_at=event.event_at,
        source_event=event,
    )
    engine = _engine(dynamic=True)
    with Session(engine) as session:
        session.add(
            ReadModelCheckpointModel(
                checkpoint_key=artifact.checkpoint_key,
                source_hash="0" * 64,
                created_at=datetime.now(UTC),
                payload={"schema_version": "old"},
            )
        )
        session.commit()

    with pytest.raises(FrozenAnalysisError, match="schema incompatible"):
        write_frozen_analysis_artifacts(engine, [artifact])
    with Session(engine) as session:
        assert session.query(DynamicPrematchEvaluationModel).count() == 0
        assert session.query(ReadModelCheckpointModel).count() == 1
        session.query(ReadModelCheckpointModel).delete()
        session.commit()

    write_frozen_analysis_artifacts(engine, [artifact])
    with Session(engine) as session:
        assert session.query(DynamicPrematchEvaluationModel).count() == 1
        assert session.query(ReadModelCheckpointModel).count() == 1


def test_checkpoint_insert_failure_rolls_back_evaluation_and_retry_is_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ready_projection(monkeypatch)
    artifact = _materializer(ScopedRepository()).build(
        "1576804",
        evaluated_at=_event().event_at,
        source_event=_event(),
    )
    engine = _engine(dynamic=True)

    def fail_checkpoint_insert(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("checkpoint insert failed")

    sa_event.listen(ReadModelCheckpointModel, "before_insert", fail_checkpoint_insert)
    try:
        with pytest.raises(RuntimeError, match="checkpoint insert failed"):
            write_frozen_analysis_artifacts(engine, [artifact])
    finally:
        sa_event.remove(ReadModelCheckpointModel, "before_insert", fail_checkpoint_insert)

    with Session(engine) as session:
        assert session.query(DynamicPrematchEvaluationModel).count() == 0
        assert session.query(DynamicPrematchSupersessionModel).count() == 0
        assert session.query(ReadModelCheckpointModel).count() == 0

    write_frozen_analysis_artifacts(engine, [artifact])
    write_frozen_analysis_artifacts(engine, [artifact])
    with Session(engine) as session:
        assert session.query(DynamicPrematchEvaluationModel).count() == 1
        assert session.query(DynamicPrematchSupersessionModel).count() == 0
        assert session.query(ReadModelCheckpointModel).count() == 1


def test_multiple_evaluation_mid_write_failure_rolls_back_entire_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ready_projection(monkeypatch)

    def calculate_two(
        repository: Any,
        fixture_id: str,
        evaluated_at: datetime,
    ) -> dict[str, Any] | None:
        card = _calculate_projection(repository, fixture_id, evaluated_at)
        assert card is not None
        totals = card["market_candidates"]["ou"]
        handicap = deepcopy(totals)
        handicap["market"] = "ASIAN_HANDICAP"
        handicap["selection"] = "HOME_AH"
        handicap["analysis_evidence"]["side_evidence"] = {
            "HOME_AH": handicap["analysis_evidence"]["side_evidence"]["OVER"]
        }
        handicap["analysis_evidence"]["quote_identity"]["quotes"] = {
            "home": handicap["analysis_evidence"]["quote_identity"]["quotes"]["over"]
        }
        handicap["analysis_evidence"]["market_probability"]["devig"] = {
            "HOME_AH": 0.52,
            "AWAY_AH": 0.48,
        }
        card["market_candidates"]["ah"] = handicap
        return card

    event = _event()
    artifact = AnalysisCardCanaryMaterializer(
        ScopedRepository(),
        calculate_analysis_card=calculate_two,
    ).build("1576804", evaluated_at=event.event_at, source_event=event)
    assert len(artifact.evaluations) == 2
    engine = _engine(dynamic=True)
    original = DynamicPrematchRepository.append_evaluation_in_session
    calls = 0

    def fail_second(
        self: DynamicPrematchRepository,
        session: Session,
        version: Any,
        *,
        supersession_reason: str = "NEW_CAPTURE_OR_MODEL_INPUT",
    ) -> tuple[Any, bool]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second evaluation failed")
        return original(
            self,
            session,
            version,
            supersession_reason=supersession_reason,
        )

    monkeypatch.setattr(
        DynamicPrematchRepository,
        "append_evaluation_in_session",
        fail_second,
    )
    with pytest.raises(RuntimeError, match="second evaluation failed"):
        write_frozen_analysis_artifacts(engine, [artifact])
    with Session(engine) as session:
        assert session.query(DynamicPrematchEvaluationModel).count() == 0
        assert session.query(DynamicPrematchSupersessionModel).count() == 0
        assert session.query(ReadModelCheckpointModel).count() == 0

    monkeypatch.setattr(
        DynamicPrematchRepository,
        "append_evaluation_in_session",
        original,
    )
    write_frozen_analysis_artifacts(engine, [artifact])
    with Session(engine) as session:
        assert session.query(DynamicPrematchEvaluationModel).count() == 2
        assert session.query(DynamicPrematchSupersessionModel).count() == 0
        assert session.query(ReadModelCheckpointModel).count() == 1


def test_checkpoint_update_failure_restores_evaluation_and_supersession(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ready_projection(monkeypatch)
    first_event = _event()
    first = _materializer(ScopedRepository()).build(
        "1576804",
        evaluated_at=first_event.event_at,
        source_event=first_event,
    )
    engine = _engine(dynamic=True)
    write_frozen_analysis_artifacts(engine, [first])

    second_event = ProjectionSourceEvent.create(
        fixture_id="1576804",
        event_type="ODDS_CHANGED",
        event_id="odds:capture-2",
        event_at=datetime(2026, 7, 18, 5, 5, tzinfo=UTC),
        payload={"capture_id": "capture-2"},
    )

    def calculate_second(
        repository: Any,
        fixture_id: str,
        evaluated_at: datetime,
    ) -> dict[str, Any] | None:
        card = _calculate_projection(repository, fixture_id, evaluated_at)
        assert card is not None
        quote = card["market_candidates"]["ou"]["analysis_evidence"]["quote_identity"]["quotes"][
            "over"
        ]
        quote["capture_id"] = "capture-2"
        quote["captured_at"] = "2026-07-18T05:04:00Z"
        return card

    second = AnalysisCardCanaryMaterializer(
        ScopedRepository(),
        calculate_analysis_card=calculate_second,
    ).build(
        "1576804",
        evaluated_at=second_event.event_at,
        source_event=second_event,
    )

    def fail_checkpoint_update(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("checkpoint update failed")

    sa_event.listen(ReadModelCheckpointModel, "before_update", fail_checkpoint_update)
    try:
        with pytest.raises(RuntimeError, match="checkpoint update failed"):
            write_frozen_analysis_artifacts(engine, [second])
    finally:
        sa_event.remove(ReadModelCheckpointModel, "before_update", fail_checkpoint_update)

    with Session(engine) as session:
        assert session.query(DynamicPrematchEvaluationModel).count() == 1
        assert session.query(DynamicPrematchSupersessionModel).count() == 0
        checkpoint = session.query(ReadModelCheckpointModel).one()
        assert checkpoint.source_hash == first.source_hash

    write_frozen_analysis_artifacts(engine, [second])
    with Session(engine) as session:
        assert session.query(DynamicPrematchEvaluationModel).count() == 2
        assert session.query(DynamicPrematchSupersessionModel).count() == 1
        checkpoint = session.query(ReadModelCheckpointModel).one()
        assert checkpoint.source_hash == second.source_hash
