from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.run_prematch_refresh import planned_task_key
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from tests.unit.test_gate_a_evidence import DIST
from tests.unit.test_gate_a_offline import (
    PUBLIC_KEY,
    PUBLIC_KEY_SHA256,
    authorization_payload,
)

from w2.config import get_settings
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.dynamic_prematch_models import (
    DynamicPrematchEvaluationModel,
    LineupConfirmedEventModel,
)
from w2.infrastructure.persistence.future_refresh_models import (
    RawPayloadModel,
)
from w2.infrastructure.persistence.matchday_intake_models import MatchdayEndpointCaptureModel
from w2.ingestion.future_refresh import FutureRefreshResult, run_future_refresh_task
from w2.operations.gate_a import GateARuntimeAuthorization, reserve_gate_a_run
from w2.operations.gate_a_evidence import GateAEvidenceError, validate_gate_a_evidence
from w2.operations.gate_a_evidence_producer import produce_gate_a_evidence
from w2.prematch.repository import ExactPairIdentity, ExactPrePostPair

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize("raw_inserted_at", [NOW, NOW - timedelta(minutes=2)])
def test_cli_plan_to_signed_reservation_audit_producer_validator_e2e(
    monkeypatch,
    tmp_path: Path,
    raw_inserted_at: datetime,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'gate-a-e2e.db'}"
    monkeypatch.setenv("W2_DATABASE_URL", database_url)
    monkeypatch.setenv("W2_FUTURE_REFRESH_PERSISTENCE", "db")
    get_settings.cache_clear()
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    task_key = planned_task_key(
        competition_id="world_cup_2026",
        season="2026",
        now=NOW - timedelta(minutes=2),
        interval_seconds=900,
    )
    authorization_file = tmp_path / "signed-authorization.json"
    trust_store = tmp_path / "trust.json"
    authorization_file.write_text(
        json.dumps(authorization_payload(task_key=task_key)), encoding="utf-8"
    )
    trust_store.write_text(
        json.dumps(
            {
                "schema_version": "w2.gate-a-authorization-trust.v1",
                "trusted_ed25519_keys": {
                    "test-independent-key": {
                        "public_key_base64": PUBLIC_KEY,
                        "public_key_sha256": PUBLIC_KEY_SHA256,
                        "custody_status": "INDEPENDENT_SIGNER_CONFIRMED",
                        "authorization_enabled": True,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    auth = GateARuntimeAuthorization.load(
        authorization_file, trust_store_path=trust_store
    )
    auth.validate_scope(
        competition_id="world_cup_2026",
        season="2026",
        persistence="db",
        task_key=task_key,
        exact_head=auth.exact_head,
        exact_tree=auth.exact_tree,
        execution_mode=auth.execution_mode,
        runtime_artifact_digest=auth.runtime_artifact_digest,
        complete_checkout_manifest_sha256=auth.complete_checkout_manifest_sha256,
        policy_season="2026",
        now=NOW,
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
    reservation = reserve_gate_a_run(auth, owner="owner", now=NOW - timedelta(minutes=1))
    with Session(engine) as session:
        session.add_all(
            [
                RawPayloadModel(
                    sha256="1" * 64,
                    endpoint="odds",
                    captured_at=NOW,
                    inserted_at=raw_inserted_at,
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
    ordinal = reservation.reserve_provider_call("odds")
    reservation.record_provider_outcome(ordinal, state="RESPONSE_RECEIVED")
    monkeypatch.setattr(
        "w2.ingestion.future_refresh.run_future_fixture_refresh",
        lambda **_kwargs: FutureRefreshResult(
            generated_at_utc=NOW,
            fixture_count=1,
            mapping_count=1,
            market_snapshot_count=1,
            feature_enrichment_payload_count=1,
            ledger_appended_count=1,
            request_count=1,
            remaining_quota=1,
            selected_market_fixture_ids=["fixture-1"],
        ),
    )
    audit = run_future_refresh_task(
        task_id="task-1",
        key=auth.task_key,
        queued_at=NOW - timedelta(minutes=2),
        now=NOW - timedelta(minutes=2),
        persistence="db",
        runtime_root=tmp_path / "runtime",
        runtime_authorization=auth,
        provider_call_reservation=reservation,
    )
    assert audit.status == "COMPLETED"
    assert audit.gate_a_authorization_id == auth.authorization_id
    assert audit.gate_a_lease_epoch == reservation.lease_epoch
    assert audit.queued_at < audit.started_at
    evidence = produce_gate_a_evidence(
        engine=engine,
        authorization_source=authorization_file,
        trust_store_path=trust_store,
    )
    if raw_inserted_at == NOW:
        assert all(
            count == {"before": 0, "after": 1, "delta": 1}
            for count in evidence["artifact_counts"].values()
        )
    else:
        assert evidence["artifact_counts"]["raw_payload"] == {
            "before": 0,
            "after": 0,
            "delta": 0,
        }
        with pytest.raises(GateAEvidenceError, match="ANY_REQUIRED_ARTIFACT_DELTA_ZERO"):
            validate_gate_a_evidence(
                evidence,
                authorization=auth,
                authorization_source_sha256=evidence["lineage"]["signed_authorization"][
                    "source_sha256"
                ],
            )
    assert evidence["lineage"]["endpoint_capture_rows"][0]["capture_id"] == "capture-post"
    assert len(evidence["lineage"]["exact_pair_source_rows"]) == 2
