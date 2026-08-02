from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.infrastructure.persistence.dynamic_prematch_models import (
    DynamicPrematchEvaluationModel,
    DynamicPrematchSupersessionModel,
    LineupConfirmedEventModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
)
from w2.operations.observability import default_metric_registry
from w2.prematch.analysis_calculator import ReadModelService
from w2.prematch.lifecycle import LineupConfirmedEvent
from w2.prematch.read_model_projection import (
    ANALYSIS_CARD_CANARY_PREFIX,
    ANALYSIS_CARD_CANARY_SCHEMA,
    ANALYSIS_CARD_SHADOW_PREFIX,
    AnalysisCardCanaryMaterializer,
    FrozenAnalysisError,
    ProjectionSourceEvent,
    _post_lineup_odds_plan,
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

    def canonical_lineup_confirmed_event(
        self,
        fixture_id: str,
    ) -> LineupConfirmedEvent | None:
        if fixture_id != self.fixture_id:
            return None
        return LineupConfirmedEvent(
            fixture_id=fixture_id,
            competition_id="league",
            season="2026",
            captured_at=datetime(2026, 7, 18, 5, 0, tzinfo=UTC),
            lineup_input_hash="lineup-1",
            home_starters=11,
            away_starters=11,
            home_lineup_identity_hash="home-lineup-1",
            away_lineup_identity_hash="away-lineup-1",
            source_capture_id="capture-1",
            raw_sha256="a" * 64,
        )

    def matchday_fixture_identity(self, fixture_id: str) -> dict[str, Any] | None:
        if fixture_id != self.fixture_id:
            return None
        return {
            "status": "READY",
            "fixture_id": fixture_id,
            "provider": "api_football",
            "provider_fixture_id": fixture_id,
            "competition_id": "league",
            "season": "2026",
        }


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
                                    "settlement_distribution": {
                                        "WIN": 0.48,
                                        "HALF_WIN": 0.10,
                                        "PUSH": 0.02,
                                        "HALF_LOSS": 0.10,
                                        "LOSS": 0.30,
                                    },
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
                                    "provider": "api_football",
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
        LineupConfirmedEventModel.__table__.create(engine)
        MatchdayCheckpointPlanModel.__table__.create(engine)
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
    event_id = (
        "lineup:lineup-1" if event_type == "LINEUP_CHANGED" else f"{event_type.lower()}:capture-1"
    )
    return ProjectionSourceEvent.create(
        fixture_id="1576804",
        event_type=event_type,
        event_id=event_id,
        event_at=datetime(2026, 7, 18, 5, 0, tzinfo=UTC),
        payload={"capture_id": "capture-1"},
    )


def _ready_policy(created_at: datetime, *, advisory_clv: float) -> dict[str, Any]:
    business_hash = canonical_sha256(
        {"created_at": created_at.isoformat(), "advisory_clv": advisory_clv}
    )
    return {
        "checkpoint_key": "performance:policy:advisory-blind-spot",
        "source_hash": business_hash,
        "created_at": created_at.isoformat(),
        "payload": {
            "schema_version": "w2.advisory_blind_spot_policy.v2",
            "status": "READY",
            "business_projection_hash": business_hash,
            "last_calibrated_at": created_at.isoformat(),
            "next_recalibration_at": (created_at + timedelta(days=90)).isoformat(),
        },
    }


def _policy_projection(state: dict[str, Any], *, strict: bool = False) -> Any:
    def calculate(
        _repository: Any,
        fixture_id: str,
        evaluated_at: datetime,
    ) -> dict[str, Any]:
        return {
            "fixture_id": fixture_id,
            "decision": "SKIP",
            "decision_tier": "NOT_READY",
            "pick": None,
            "evaluated_at": evaluated_at.isoformat(),
            "lineup_provenance": {
                "requirement": "STRICT" if strict else "ADVISORY",
            },
            "advisory_blind_spot_policy": state["policy"],
        }

    return calculate


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


def test_advisory_policy_identity_changes_source_and_rematerializes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluated_at = datetime(2026, 7, 18, 5, 0, tzinfo=UTC)
    monkeypatch.setattr(
        "w2.prematch.read_model_projection.validate_advisory_blind_spot_policy",
        lambda *_args, **_kwargs: True,
    )
    state = {"policy": _ready_policy(evaluated_at - timedelta(days=1), advisory_clv=0.05)}
    materializer = AnalysisCardCanaryMaterializer(
        ScopedRepository(),
        calculate_analysis_card=_policy_projection(state),
    )
    first = materializer.build("1576804", evaluated_at=evaluated_at)
    state["policy"] = _ready_policy(evaluated_at, advisory_clv=0.08)
    second = materializer.build("1576804", evaluated_at=evaluated_at)
    replay = materializer.build("1576804", evaluated_at=evaluated_at)
    engine = _engine()

    write_frozen_analysis_artifacts(engine, [first])
    write_frozen_analysis_artifacts(engine, [second])
    write_frozen_analysis_artifacts(engine, [replay])

    first_identity = first.payload["input_manifest"]["advisory_policy_identity"]
    second_identity = second.payload["input_manifest"]["advisory_policy_identity"]
    assert first_identity["validation_status"] == "VALID"
    assert second_identity["validation_status"] == "VALID"
    assert first_identity["identity_hash"] != second_identity["identity_hash"]
    assert first.source_hash != second.source_hash
    assert first.artifact_hash != second.artifact_hash
    assert replay.source_hash == second.source_hash
    assert replay.artifact_hash == second.artifact_hash
    with Session(engine) as session:
        checkpoint = session.query(ReadModelCheckpointModel).one()
    assert checkpoint.source_hash == second.source_hash


def test_strict_frozen_artifact_does_not_drift_with_advisory_policy() -> None:
    evaluated_at = datetime(2026, 7, 18, 5, 0, tzinfo=UTC)
    state = {"policy": _ready_policy(evaluated_at - timedelta(days=1), advisory_clv=0.05)}
    materializer = AnalysisCardCanaryMaterializer(
        ScopedRepository(),
        calculate_analysis_card=_policy_projection(state, strict=True),
    )
    first = materializer.build("1576804", evaluated_at=evaluated_at)
    state["policy"] = _ready_policy(evaluated_at, advisory_clv=0.08)
    second = materializer.build("1576804", evaluated_at=evaluated_at)

    assert first.payload["input_manifest"]["advisory_policy_identity"] == {
        "applicability": "NOT_APPLICABLE_STRICT"
    }
    assert first.source_hash == second.source_hash
    assert first.artifact_hash == second.artifact_hash


@pytest.mark.parametrize(
    ("policy", "status"),
    (
        ({}, "MISSING"),
        ({"checkpoint_key": "wrong", "payload": {}}, "INVALID"),
        (
            _ready_policy(
                datetime(2026, 7, 18, 5, 0, tzinfo=UTC),
                advisory_clv=0.05,
            ),
            "INVALID",
        ),
    ),
)
def test_advisory_policy_provenance_records_fail_closed_status(
    policy: dict[str, Any],
    status: str,
) -> None:
    evaluated_at = datetime(2026, 7, 18, 4, 59, 59, 999999, tzinfo=UTC)
    artifact = AnalysisCardCanaryMaterializer(
        ScopedRepository(),
        calculate_analysis_card=_policy_projection({"policy": policy}),
    ).build("1576804", evaluated_at=evaluated_at)

    identity = artifact.payload["input_manifest"]["advisory_policy_identity"]
    assert identity["validation_status"] == status
    assert identity["identity_hash"]


def test_public_and_shadow_record_same_advisory_policy_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluated_at = datetime(2026, 7, 18, 5, 0, tzinfo=UTC)
    state = {"policy": _ready_policy(evaluated_at, advisory_clv=0.05)}
    monkeypatch.setattr(
        "w2.prematch.read_model_projection.validate_advisory_blind_spot_policy",
        lambda *_args, **_kwargs: True,
    )
    _patch_ready_projection(monkeypatch)

    def calculate(
        repository: Any,
        fixture_id: str,
        as_of: datetime,
    ) -> dict[str, Any]:
        card = _calculate_projection(repository, fixture_id, as_of)
        assert card is not None
        card["lineup_provenance"] = {"requirement": "ADVISORY"}
        card["advisory_blind_spot_policy"] = state["policy"]
        return card

    materializer = AnalysisCardCanaryMaterializer(
        ScopedRepository(),
        calculate_analysis_card=calculate,
    )

    public = materializer.build("1576804", evaluated_at=evaluated_at)
    shadow = materializer.build(
        "1576804",
        evaluated_at=evaluated_at,
        source_event=_event(),
    )

    assert (
        public.payload["input_manifest"]["advisory_policy_identity"]
        == shadow.payload["input_manifest"]["advisory_policy_identity"]
    )


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
    materializer = _materializer(ScopedRepository())
    artifact = materializer.build(
        "1576804",
        evaluated_at=datetime(2026, 7, 18, 5, 0, tzinfo=UTC),
    )
    replay = materializer.build(
        "1576804",
        evaluated_at=datetime(2026, 7, 18, 5, 0, tzinfo=UTC),
    )
    assert replay.checkpoint_key == artifact.checkpoint_key
    assert replay.source_hash == artifact.source_hash
    assert replay.artifact_hash == artifact.artifact_hash
    assert replay.canonical_bytes == artifact.canonical_bytes
    engine = _engine()
    registry = default_metric_registry()
    hit_key = ("w2_checkpoint_reads_total", (("status", "HIT"),))
    invalid_key = ("w2_checkpoint_reads_total", (("status", "INVALID"),))
    hits_before = registry.labelled_counters.get(hit_key, 0)
    invalid_before = registry.labelled_counters.get(invalid_key, 0)

    write_frozen_analysis_artifacts(engine, [artifact])
    write_frozen_analysis_artifacts(engine, [replay])
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
    with pytest.raises(FrozenAnalysisError, match="artifact hash mismatch"):
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


def test_payload_validation_rejects_advisory_policy_identity_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_projection(monkeypatch)
    artifact = _materializer(ScopedRepository()).build(
        "1576804",
        evaluated_at=datetime(2026, 7, 18, 5, 0, tzinfo=UTC),
    )
    body = deepcopy(artifact.payload)
    body.pop("artifact_hash")
    body["input_manifest"]["advisory_policy_identity"]["validation_status"] = "VALID"
    identity = body["input_manifest"]["advisory_policy_identity"]
    identity["identity_hash"] = canonical_sha256(
        {key: value for key, value in identity.items() if key != "identity_hash"}
    )
    payload = {**body, "artifact_hash": canonical_sha256(body)}

    with pytest.raises(FrozenAnalysisError, match="policy identity mismatch"):
        validate_frozen_analysis_payload("1576804", payload)


def test_public_projection_preserves_original_active_payload_and_hash_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_projection(monkeypatch)
    artifact = _materializer(ScopedRepository()).build(
        "1576804",
        evaluated_at=datetime(2026, 7, 18, 5, 0, tzinfo=UTC),
    )
    artifact_body = {
        key: value for key, value in artifact.payload.items() if key != "artifact_hash"
    }

    assert artifact.payload["checkpoint_namespace"] == "public"
    assert set(artifact.payload) == {
        "schema_version",
        "checkpoint_namespace",
        "fixture_identity",
        "input_manifest",
        "analysis_card",
        "artifact_hash",
    }
    assert artifact.source_hash == canonical_sha256(artifact.payload["input_manifest"])
    assert artifact.payload["artifact_hash"] == canonical_sha256(artifact_body)
    validated = validate_frozen_analysis_payload("1576804", artifact.payload)
    assert validated.source_hash == artifact.source_hash
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


def test_shadow_reconciliation_reports_real_difference_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ready_projection(monkeypatch)
    calls = 0

    def calculate(
        repository: Any,
        fixture_id: str,
        evaluated_at: datetime,
    ) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        card = _calculate_projection(repository, fixture_id, evaluated_at)
        assert card is not None
        card["decision"] = "SKIP" if calls == 1 else "ANALYSIS_ONLY"
        return card

    artifact = AnalysisCardCanaryMaterializer(
        ScopedRepository(),
        calculate_analysis_card=calculate,
    ).build(
        "1576804",
        evaluated_at=_event().event_at,
        source_event=_event(),
    )

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


def test_not_ready_model_without_distribution_writes_ineligible_v1_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ready_projection(monkeypatch)

    def calculate(
        repository: Any,
        fixture_id: str,
        evaluated_at: datetime,
    ) -> dict[str, Any] | None:
        card = _calculate_projection(repository, fixture_id, evaluated_at)
        assert card is not None
        model = card["market_candidates"]["ou"]["analysis_evidence"]["side_evidence"][
            "OVER"
        ]["model_probability"]
        model["status"] = "NOT_READY"
        model.pop("settlement_distribution")
        return card

    event = _event()
    artifact = AnalysisCardCanaryMaterializer(
        ScopedRepository(),
        calculate_analysis_card=calculate,
    ).build(
        "1576804",
        evaluated_at=event.event_at,
        source_event=event,
    )

    assert len(artifact.evaluations) == 1
    marker = artifact.evaluations[0]
    assert marker.schema_version == "w2.dynamic_quote_evaluation.v1"
    assert marker.state.value == "NOT_READY_MODEL_INPUT"
    assert marker.model_settlement_distribution is None


def test_ready_model_without_distribution_remains_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ready_projection(monkeypatch)

    def calculate(
        repository: Any,
        fixture_id: str,
        evaluated_at: datetime,
    ) -> dict[str, Any] | None:
        card = _calculate_projection(repository, fixture_id, evaluated_at)
        assert card is not None
        card["market_candidates"]["ou"]["analysis_evidence"]["side_evidence"]["OVER"][
            "model_probability"
        ].pop("settlement_distribution")
        return card

    event = _event()
    with pytest.raises(
        ValueError,
        match="DYNAMIC_EVALUATION_V2_DISTRIBUTION_INVALID",
    ):
        AnalysisCardCanaryMaterializer(
            ScopedRepository(),
            calculate_analysis_card=calculate,
        ).build(
            "1576804",
            evaluated_at=event.event_at,
            source_event=event,
        )


def test_lineup_odds_plan_replay_is_zero_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ready_projection(monkeypatch)
    event = _event("LINEUP_CHANGED")
    artifact = _materializer(ScopedRepository()).build(
        "1576804",
        evaluated_at=event.event_at,
        source_event=event,
    )
    engine = _engine(dynamic=True)

    write_frozen_analysis_artifacts(engine, [artifact])
    write_frozen_analysis_artifacts(engine, [artifact])

    with Session(engine) as session:
        assert session.query(MatchdayCheckpointPlanModel).count() == 1
        plan = session.query(MatchdayCheckpointPlanModel).one()
        assert plan.checkpoint == "LINEUP_CONFIRMED"
        assert plan.endpoints == ["odds"]
        assert plan.status == "DUE"


@pytest.mark.parametrize("advanced_status", ["CLAIMED", "CAPTURED", "MISSED"])
def test_lineup_odds_plan_replay_preserves_advanced_state(
    monkeypatch: pytest.MonkeyPatch,
    advanced_status: str,
) -> None:
    _patch_ready_projection(monkeypatch)
    event = _event("LINEUP_CHANGED")
    artifact = _materializer(ScopedRepository()).build(
        "1576804",
        evaluated_at=event.event_at,
        source_event=event,
    )
    engine = _engine(dynamic=True)
    write_frozen_analysis_artifacts(engine, [artifact])

    with Session(engine) as session:
        plan = session.query(MatchdayCheckpointPlanModel).one()
        plan.status = advanced_status
        plan.missed_at = datetime(2026, 7, 18, 6, 0, tzinfo=UTC)
        plan.capture_id = "capture-advanced"
        plan.current_unscheduled_capture_id = "capture-unscheduled"
        plan.blockers = ["ADVANCED_STATE"]
        plan.plan_hash = "f" * 64
        session.commit()

    write_frozen_analysis_artifacts(engine, [artifact])

    with Session(engine) as session:
        plan = session.query(MatchdayCheckpointPlanModel).one()
        assert plan.status == advanced_status
        assert plan.missed_at == datetime(2026, 7, 18, 6, 0)
        assert plan.capture_id == "capture-advanced"
        assert plan.current_unscheduled_capture_id == "capture-unscheduled"
        assert plan.blockers == ["ADVANCED_STATE"]
        assert plan.plan_hash == "f" * 64


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("endpoints", ("odds", "fixtures")),
        ("window_end", datetime(2026, 7, 19, 11, 59, tzinfo=UTC)),
        ("kickoff_utc", datetime(2026, 7, 19, 12, 1, tzinfo=UTC)),
    ],
)
def test_lineup_odds_plan_spec_conflict_rolls_back_projection_unit(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    _patch_ready_projection(monkeypatch)
    event = _event("LINEUP_CHANGED")
    artifact = _materializer(ScopedRepository()).build(
        "1576804",
        evaluated_at=event.event_at,
        source_event=event,
    )
    assert artifact.lineup_event is not None
    fixture_identity = artifact.payload["fixture_identity"]
    intended = _post_lineup_odds_plan(artifact.lineup_event, fixture_identity)
    conflicting = {**intended, field: value}
    engine = _engine(dynamic=True)
    natural_identity = ":".join(
        str(conflicting[key])
        for key in (
            "fixture_id",
            "competition_id",
            "season",
            "checkpoint",
            "policy_version",
        )
    )
    plan_times = {
        key: (
            value
            if isinstance((value := conflicting[key]), datetime)
            else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        )
        for key in ("kickoff_utc", "scheduled_at", "window_start", "window_end")
    }
    with Session(engine) as session:
        session.add(
            MatchdayCheckpointPlanModel(
                plan_id=canonical_sha256(natural_identity),
                fixture_id=str(conflicting["fixture_id"]),
                competition_id=str(conflicting["competition_id"]),
                season=str(conflicting["season"]),
                policy_version=str(conflicting["policy_version"]),
                checkpoint=str(conflicting["checkpoint"]),
                kickoff_utc=plan_times["kickoff_utc"],
                scheduled_at=plan_times["scheduled_at"],
                window_start=plan_times["window_start"],
                window_end=plan_times["window_end"],
                endpoints=list(conflicting["endpoints"]),
                status=str(conflicting["status"]),
                missed_at=conflicting["missed_at"],
                capture_id=conflicting["capture_id"],
                current_unscheduled_capture_id=conflicting[
                    "current_unscheduled_capture_id"
                ],
                blockers=list(conflicting["blockers"]),
                plan_hash=str(conflicting["plan_hash"]),
            )
        )
        session.commit()

    with pytest.raises(RuntimeError, match="CHECKPOINT_PLAN_CONFLICT"):
        write_frozen_analysis_artifacts(engine, [artifact])

    with Session(engine) as session:
        assert session.query(LineupConfirmedEventModel).count() == 0
        assert session.query(MatchdayCheckpointPlanModel).count() == 1
        assert session.query(DynamicPrematchEvaluationModel).count() == 0
        assert session.query(DynamicPrematchSupersessionModel).count() == 0
        assert session.query(ReadModelCheckpointModel).count() == 0


@pytest.mark.parametrize(
    "event_type",
    ["ODDS_CHANGED", "LINEUP_CHANGED", "FIXTURE_CHANGED"],
)
def test_single_event_shadow_matches_post_write_current_read_with_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    event_type: str,
) -> None:
    _patch_ready_projection(monkeypatch)
    engine = _engine(dynamic=True)

    class CurrentReadRepository(ScopedRepository):
        def dynamic_prematch_lifecycle(self, fixture_id: str) -> dict[str, Any]:
            return DynamicPrematchRepository(engine).lifecycle(fixture_id)

    repository = CurrentReadRepository()

    def calculate(
        scoped_repository: Any,
        fixture_id: str,
        evaluated_at: datetime,
    ) -> dict[str, Any] | None:
        card = _calculate_projection(scoped_repository, fixture_id, evaluated_at)
        assert card is not None
        lifecycle = scoped_repository.dynamic_prematch_lifecycle(fixture_id)
        if lifecycle.get("versions"):
            card["dynamic_prematch"] = lifecycle
        return card

    event = _event(event_type)
    materializer = AnalysisCardCanaryMaterializer(
        repository,
        calculate_analysis_card=calculate,
    )
    artifact = materializer.build(
        "1576804",
        evaluated_at=event.event_at,
        source_event=event,
    )

    write_frozen_analysis_artifacts(engine, [artifact])

    persisted = read_shadow_analysis_artifact(engine, "1576804")
    current = calculate(repository, "1576804", event.event_at)
    assert persisted is not None
    assert current is not None
    assert persisted.payload["analysis_card"] == current
    assert persisted.payload["analysis_card"]["dynamic_prematch"]["versions"]
    assert persisted.payload["shadow_reconciliation"] == {
        "read_time_hash": canonical_sha256(current),
        "projected_hash": canonical_sha256(current),
        "match": True,
        "differences": [],
    }
    with Session(engine) as session:
        assert session.query(DynamicPrematchEvaluationModel).count() == 1
        assert session.query(DynamicPrematchSupersessionModel).count() == 0
        assert session.query(ReadModelCheckpointModel).count() == 1
        assert session.query(LineupConfirmedEventModel).count() == (
            1 if event_type == "LINEUP_CHANGED" else 0
        )
        assert session.query(MatchdayCheckpointPlanModel).count() == (
            1 if event_type == "LINEUP_CHANGED" else 0
        )
        evaluation = session.query(DynamicPrematchEvaluationModel).one()
        assert evaluation.payload["schema_version"] == "w2.dynamic_quote_evaluation.v2"
        assert evaluation.payload["competition_id"] == "league"
        assert evaluation.payload["season"] == "2026"
        assert evaluation.payload["provider"] == "api_football"
        assert evaluation.payload["lineup_input_hash"] is None
        assert evaluation.payload["state"] == "ANALYSIS_PICK_ACTIVE"
        assert evaluation.payload["model_settlement_distribution"] == {
            "WIN": 0.48,
            "HALF_WIN": 0.10,
            "PUSH": 0.02,
            "HALF_LOSS": 0.10,
            "LOSS": 0.30,
        }
    if event_type == "LINEUP_CHANGED":
        assert len(artifact.payload["lineup_event_payload_sha256"]) == 64
        with Session(engine) as session:
            plan = session.query(MatchdayCheckpointPlanModel).one()
            assert plan.checkpoint == "LINEUP_CONFIRMED"
            assert plan.endpoints == ["odds"]
            assert plan.scheduled_at == datetime(2026, 7, 18, 5, 0)
            assert plan.status == "DUE"
    else:
        assert "lineup_event_payload_sha256" not in artifact.payload


def test_lineup_source_event_binding_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ready_projection(monkeypatch)
    repository = ScopedRepository()
    materializer = _materializer(repository)
    event = _event("LINEUP_CHANGED")

    wrong_id = ProjectionSourceEvent.create(
        fixture_id=event.fixture_id,
        event_type=event.event_type,
        event_id="lineup:wrong",
        event_at=event.event_at,
        payload={},
    )
    with pytest.raises(FrozenAnalysisError, match="lineup event id mismatch"):
        materializer.build(
            "1576804",
            evaluated_at=wrong_id.event_at,
            source_event=wrong_id,
        )

    wrong_time = ProjectionSourceEvent.create(
        fixture_id=event.fixture_id,
        event_type=event.event_type,
        event_id=event.event_id,
        event_at=event.event_at + timedelta(microseconds=1),
        payload={},
    )
    with pytest.raises(FrozenAnalysisError, match="lineup event time mismatch"):
        materializer.build(
            "1576804",
            evaluated_at=wrong_time.event_at,
            source_event=wrong_time,
        )

    class WrongFixtureRepository(ScopedRepository):
        def canonical_lineup_confirmed_event(
            self,
            fixture_id: str,
        ) -> LineupConfirmedEvent | None:
            original = super().canonical_lineup_confirmed_event(fixture_id)
            assert original is not None
            return LineupConfirmedEvent(**{**original.__dict__, "fixture_id": "other-fixture"})

    with pytest.raises(FrozenAnalysisError, match="lineup event fixture mismatch"):
        _materializer(WrongFixtureRepository()).build(
            "1576804",
            evaluated_at=event.event_at,
            source_event=event,
        )


def test_lineup_event_and_shadow_unit_roll_back_on_checkpoint_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ready_projection(monkeypatch)
    event = _event("LINEUP_CHANGED")
    artifact = _materializer(ScopedRepository()).build(
        "1576804",
        evaluated_at=event.event_at,
        source_event=event,
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
        assert session.query(LineupConfirmedEventModel).count() == 0
        assert session.query(MatchdayCheckpointPlanModel).count() == 0
        assert session.query(DynamicPrematchEvaluationModel).count() == 0
        assert session.query(DynamicPrematchSupersessionModel).count() == 0
        assert session.query(ReadModelCheckpointModel).count() == 0

    write_frozen_analysis_artifacts(engine, [artifact])
    with Session(engine) as session:
        assert session.query(LineupConfirmedEventModel).count() == 1
        assert session.query(MatchdayCheckpointPlanModel).count() == 1
        assert session.query(DynamicPrematchEvaluationModel).count() == 1
        assert session.query(ReadModelCheckpointModel).count() == 1


def test_lineup_shadow_payload_requires_event_payload_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ready_projection(monkeypatch)
    event = _event("LINEUP_CHANGED")
    artifact = _materializer(ScopedRepository()).build(
        "1576804",
        evaluated_at=event.event_at,
        source_event=event,
    )
    payload = deepcopy(artifact.payload)
    payload.pop("lineup_event_payload_sha256")

    with pytest.raises(FrozenAnalysisError, match="lineup event payload identity missing"):
        validate_frozen_analysis_payload("1576804", payload)


def test_post_write_current_read_difference_rolls_back_entire_shadow_unit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ready_projection(monkeypatch)
    engine = _engine(dynamic=True)
    calls = 0

    def calculate(
        scoped_repository: Any,
        fixture_id: str,
        evaluated_at: datetime,
    ) -> dict[str, Any] | None:
        nonlocal calls
        calls += 1
        card = _calculate_projection(scoped_repository, fixture_id, evaluated_at)
        assert card is not None
        lifecycle = scoped_repository.dynamic_prematch_lifecycle(fixture_id)
        if lifecycle.get("versions"):
            card["dynamic_prematch"] = lifecycle
        card["decision"] = "ANALYSIS_ONLY" if calls <= 4 else "SKIP"
        return card

    event = _event()
    artifact = AnalysisCardCanaryMaterializer(
        ScopedRepository(),
        calculate_analysis_card=calculate,
    ).build(
        "1576804",
        evaluated_at=event.event_at,
        source_event=event,
    )

    with pytest.raises(
        FrozenAnalysisError,
        match="persisted-readback reconciliation mismatch:decision",
    ):
        write_frozen_analysis_artifacts(engine, [artifact])

    with Session(engine) as session:
        assert session.query(DynamicPrematchEvaluationModel).count() == 0
        assert session.query(DynamicPrematchSupersessionModel).count() == 0
        assert session.query(ReadModelCheckpointModel).count() == 0


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

    event = _event("LINEUP_CHANGED")
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
        assert session.query(LineupConfirmedEventModel).count() == 0
        assert session.query(MatchdayCheckpointPlanModel).count() == 0
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
        assert session.query(LineupConfirmedEventModel).count() == 1
        assert session.query(MatchdayCheckpointPlanModel).count() == 1
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
        latest = (
            session.query(DynamicPrematchEvaluationModel)
            .order_by(DynamicPrematchEvaluationModel.capture_at.desc())
            .first()
        )
        assert latest is not None
        assert latest.payload["lineup_input_hash"] == "lineup-1"
        checkpoint = session.query(ReadModelCheckpointModel).one()
        assert checkpoint.source_hash == second.source_hash
