from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from tests.unit.test_gate_a_evidence import DIST, authorization

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.dynamic_prematch_models import (
    DynamicPrematchEvaluationModel,
    LineupConfirmedEventModel,
)
from w2.infrastructure.persistence.future_refresh_models import (
    FutureRefreshTaskAuditModel,
    GateAProviderCallModel,
    GateARunReservationModel,
    RawPayloadModel,
)
from w2.infrastructure.persistence.matchday_intake_models import MatchdayEndpointCaptureModel
from w2.operations.gate_a_evidence_producer import produce_gate_a_evidence
from w2.prematch.repository import ExactPairIdentity, ExactPrePostPair

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


def test_unique_producer_derives_counts_and_concrete_lineage(
    monkeypatch,
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    auth = authorization()
    monkeypatch.setattr(
        "w2.operations.gate_a.GateARuntimeAuthorization.load",
        lambda _path: auth,
    )
    identity = ExactPairIdentity(
        canonical_fixture_id="fixture-1",
        competition_id="world_cup_2026",
        season_id="2026",
        provider_id="api_football",
        bookmaker_id="book-1",
        market="ASIAN_HANDICAP",
        selection="HOME",
        exact_line=-0.25,
        pre_evaluation_id="eval-pre",
        post_evaluation_id="eval-post",
    )
    pair = ExactPrePostPair(
        identity=identity,
        identity_hash=identity.identity_hash,
        hash_domain="eval_02b.pair_identity",
        serializer_version="w2.canonical-json.v2",
        kickoff_at=NOW + timedelta(hours=1),
        lineup_confirmed_at=NOW - timedelta(minutes=1),
        pre_evaluated_at=NOW - timedelta(minutes=2),
        pre_capture_at=NOW - timedelta(minutes=2),
        post_evaluated_at=NOW,
        post_capture_at=NOW,
        lineup_input_hash="lineup-hash",
        pre_capture_id="capture-pre",
        post_capture_id="capture-post",
        pre_quote_identity_hash="quote-pre",
        post_quote_identity_hash="quote-post",
        pre_superseded_by_evaluation_id=None,
        post_superseded_by_evaluation_id=None,
        baseline_distribution=DIST,
        candidate_distribution=DIST,
    )
    monkeypatch.setattr(
        "w2.operations.gate_a_evidence_producer.project_exact_eval_02b_pairs",
        lambda _engine: SimpleNamespace(pairs=(pair,)),
    )
    with Session(engine) as session:
        session.add_all(
            [
                GateARunReservationModel(
                    authorization_id=auth.authorization_id,
                    task_key=auth.task_key,
                    competition_id=auth.competition_id,
                    season=auth.season,
                    exact_head=auth.exact_head,
                    exact_tree=auth.exact_tree,
                    execution_mode=auth.execution_mode,
                    runtime_artifact_digest=None,
                    complete_checkout_manifest_sha256=auth.complete_checkout_manifest_sha256,
                    evidence_baseline={
                        name: []
                        for name in (
                            "provider_calls",
                            "raw_payload",
                            "endpoint_capture",
                            "lineup_event",
                            "dynamic_evaluation_v2",
                            "five_state_snapshot",
                            "exact_pair",
                            "bootstrap_seed_evidence",
                        )
                    },
                    owner="owner",
                    reserved_at=NOW - timedelta(minutes=1),
                    finished_at=NOW + timedelta(minutes=1),
                    status="COMPLETED",
                    provider_call_cap=4,
                    provider_calls_used=1,
                    last_endpoint="odds",
                ),
                FutureRefreshTaskAuditModel(
                    task_id="task-1",
                    key=auth.task_key,
                    owner="owner",
                    queued_at=NOW - timedelta(minutes=1),
                    started_at=NOW - timedelta(seconds=30),
                    finished_at=NOW + timedelta(seconds=30),
                    status="COMPLETED",
                    result={"fixture_count": 1},
                ),
                RawPayloadModel(
                    sha256="1" * 64,
                    endpoint="odds",
                    captured_at=NOW,
                    storage_uri="db://raw_payload/1",
                    payload={"response": []},
                ),
                MatchdayEndpointCaptureModel(
                    capture_id="capture-post",
                    fixture_id="fixture-1",
                    competition_id="world_cup_2026",
                    checkpoint="LINEUP_CONFIRMED",
                    endpoint="odds",
                    sanitized_params={},
                    params_hash="2" * 64,
                    request_task_key=auth.task_key,
                    attempt=1,
                    requested_at=NOW,
                    provider_captured_at=NOW,
                    status_code=200,
                    elapsed_ms=1,
                    response_count=1,
                    quota_values={},
                    raw_payload_sha256="1" * 64,
                    capture_status="CAPTURED",
                ),
                LineupConfirmedEventModel(
                    event_id="lineup-event-1",
                    fixture_id="fixture-1",
                    lineup_input_hash="lineup-hash",
                    captured_at=NOW,
                    checkpoint="LINEUP_CONFIRMED",
                    payload={
                        "source_capture_id": "capture-post",
                        "raw_sha256": "1" * 64,
                    },
                ),
            ]
        )
        session.flush()
        reservation = session.query(GateARunReservationModel).one()
        session.add(
            GateAProviderCallModel(
                lease_epoch=reservation.lease_epoch,
                call_ordinal=1,
                endpoint="odds",
                state="RESPONSE_RECEIVED",
                reserved_at=NOW,
                finished_at=NOW,
            )
        )
        for evaluation_id, capture_id, capture_at in (
            ("eval-pre", "capture-pre", NOW - timedelta(minutes=2)),
            ("eval-post", "capture-post", NOW),
        ):
            session.add(
                DynamicPrematchEvaluationModel(
                    evaluation_id=evaluation_id,
                    identity_hash=(evaluation_id + "0" * 64)[:64],
                    fixture_id="fixture-1",
                    market="ASIAN_HANDICAP",
                    selection="HOME",
                    checkpoint="LINEUP_CONFIRMED",
                    capture_id=capture_id,
                    quote_identity_hash=f"quote-{evaluation_id}",
                    model_input_hash="3" * 64,
                    lineup_input_hash=("lineup-hash" if evaluation_id == "eval-post" else None),
                    evaluated_at=capture_at,
                    capture_at=capture_at,
                    original_state="ANALYSIS_PICK_ACTIVE",
                    payload={
                        "schema_version": "w2.dynamic_quote_evaluation.v2",
                        "provider": "api_football",
                        "bookmaker_id": "book-1",
                        "exact_line": -0.25,
                        "model_settlement_distribution": DIST,
                    },
                )
            )
        session.commit()
    authorization_file = tmp_path / "signed-authorization.json"
    authorization_file.write_text('{"signed":true}', encoding="utf-8")
    evidence = produce_gate_a_evidence(
        engine=engine,
        authorization_source=authorization_file,
    )
    assert all(
        count == {"before": 0, "after": 1, "delta": 1}
        for count in evidence["artifact_counts"].values()
    )
    assert evidence["lineage"]["endpoint_capture_rows"][0]["capture_id"] == "capture-post"
    assert len(evidence["lineage"]["exact_pair_source_rows"]) == 2
