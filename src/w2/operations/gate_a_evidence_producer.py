from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import HashDomain, canonical_sha256, eval_02b_bootstrap_seed
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
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayEndpointCaptureModel,
    MatchdayFixtureIdentityModel,
)
from w2.operations.gate_a import (
    GATE_A_OWNER_APPROVAL_MODE,
    GateAError,
    GateARuntimeAuthorization,
    select_fixture_from_authorization,
)
from w2.operations.gate_a_evidence import (
    GATE_A_EVIDENCE_SCHEMA,
    SERIALIZER_VERSION,
    GateAEvidenceError,
)
from w2.prematch.repository import project_exact_eval_02b_pairs

BOOTSTRAP_CONTRACT_VERSION = "w2.eval_02b_gate.v1"
DYNAMIC_V2_SCHEMA = "w2.dynamic_quote_evaluation.v2"
FIVE_STATE_KEYS = ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")
BASELINE_KEYS = {
    "provider_calls",
    "raw_payload",
    "endpoint_capture",
    "lineup_event",
    "dynamic_evaluation_v2",
    "five_state_snapshot",
    "exact_pair",
    "bootstrap_seed_evidence",
}


def capture_gate_a_evidence_baseline(
    engine: Engine,
    authorization: GateARuntimeAuthorization,
) -> dict[str, list[str]]:
    """Persist task-scoped authority IDs before the one-shot reservation exists."""
    with Session(engine) as session:
        captures = list(
            session.scalars(
                select(MatchdayEndpointCaptureModel).where(
                    MatchdayEndpointCaptureModel.request_task_key == authorization.task_key
                )
            )
        )
        raw_hashes = {row.raw_payload_sha256 for row in captures}
        fixture_ids = _authorized_fixture_aliases(authorization) | {
            str(row.fixture_id) for row in captures if row.fixture_id
        }
        lineup_rows = (
            list(
                session.scalars(
                    select(LineupConfirmedEventModel).where(
                        LineupConfirmedEventModel.fixture_id.in_(fixture_ids)
                    )
                )
            )
            if fixture_ids
            else []
        )
        dynamic_rows = (
            list(
                session.scalars(
                    select(DynamicPrematchEvaluationModel).where(
                        DynamicPrematchEvaluationModel.fixture_id.in_(fixture_ids)
                    )
                )
            )
            if fixture_ids
            else []
        )
    capture_ids = {row.capture_id for row in captures}
    pairs = [
        pair
        for pair in project_exact_eval_02b_pairs(engine).pairs
        if pair.identity.canonical_fixture_id in fixture_ids and pair.post_capture_id in capture_ids
    ]
    pair_hashes = [pair.identity_hash for pair in pairs]
    return {
        "provider_calls": [],
        "raw_payload": sorted(raw_hashes),
        "endpoint_capture": sorted(capture_ids),
        "lineup_event": sorted(row.event_id for row in lineup_rows),
        "dynamic_evaluation_v2": sorted(
            row.evaluation_id
            for row in dynamic_rows
            if row.payload.get("schema_version") == DYNAMIC_V2_SCHEMA
        ),
        "five_state_snapshot": sorted(
            row.evaluation_id
            for row in dynamic_rows
            if row.payload.get("schema_version") == DYNAMIC_V2_SCHEMA
            and _valid_five_state(row.payload.get("model_settlement_distribution"))
        ),
        "exact_pair": sorted(pair_hashes),
        "bootstrap_seed_evidence": (
            [str(eval_02b_bootstrap_seed(pair_hashes, contract_version=BOOTSTRAP_CONTRACT_VERSION))]
            if pair_hashes
            else []
        ),
    }


def produce_gate_a_evidence(
    *,
    engine: Engine,
    authorization_source: Path,
    trust_store_path: Path | None = None,
) -> dict[str, Any]:
    """Build the sole Gate-A evidence package directly from signed and DB authorities."""
    authorization = GateARuntimeAuthorization.load(
        authorization_source,
        **({"trust_store_path": trust_store_path} if trust_store_path is not None else {}),
    )
    with Session(engine) as session:
        reservation = session.scalar(
            select(GateARunReservationModel).where(
                GateARunReservationModel.authorization_id == authorization.authorization_id
            )
        )
        if (
            reservation is None
            or reservation.status != "COMPLETED"
            or reservation.finished_at is None
        ):
            raise GateAEvidenceError("GATE_A_RESERVATION_NOT_COMPLETED")
        _reservation_matches_authorization(reservation, authorization)
        baseline = reservation.evidence_baseline
        if (
            not isinstance(baseline, dict)
            or set(baseline) != BASELINE_KEYS
            or any(not isinstance(values, list) for values in baseline.values())
        ):
            raise GateAEvidenceError("GATE_A_EVIDENCE_BASELINE_INVALID")
        audits = list(
            session.scalars(
                select(FutureRefreshTaskAuditModel).where(
                    FutureRefreshTaskAuditModel.key == authorization.task_key,
                    FutureRefreshTaskAuditModel.gate_a_authorization_id
                    == authorization.authorization_id,
                    FutureRefreshTaskAuditModel.gate_a_lease_epoch == reservation.lease_epoch,
                    FutureRefreshTaskAuditModel.status == "COMPLETED",
                )
            )
        )
        if len(audits) != 1:
            raise GateAEvidenceError("GATE_A_TASK_AUDIT_NOT_COMPLETED")
        audit = audits[0]
        provider_calls = list(
            session.scalars(
                select(GateAProviderCallModel)
                .where(GateAProviderCallModel.lease_epoch == reservation.lease_epoch)
                .order_by(GateAProviderCallModel.call_ordinal)
            )
        )
        all_captures = list(
            session.scalars(
                select(MatchdayEndpointCaptureModel)
                .where(MatchdayEndpointCaptureModel.request_task_key == authorization.task_key)
                .order_by(MatchdayEndpointCaptureModel.capture_id)
            )
        )
        all_raw_hashes = {row.raw_payload_sha256 for row in all_captures}
        all_raw_rows = (
            list(
                session.scalars(
                    select(RawPayloadModel)
                    .where(RawPayloadModel.sha256.in_(all_raw_hashes))
                    .order_by(RawPayloadModel.sha256)
                )
            )
            if all_raw_hashes
            else []
        )
        discovery_capture = next(
            (
                row
                for row in all_captures
                if row.capture_id == reservation.fixture_discovery_capture_id
            ),
            None,
        )
        raw_by_sha = {row.sha256: row for row in all_raw_rows}
        discovery_raw = (
            raw_by_sha.get(discovery_capture.raw_payload_sha256)
            if discovery_capture is not None
            else None
        )
        if discovery_capture is None or discovery_raw is None:
            raise GateAEvidenceError("GATE_A_FIXTURE_DISCOVERY_LINEAGE_INVALID")
        try:
            fixture_selection = select_fixture_from_authorization(
                discovery_raw.payload,
                authorization,
            )
        except GateAError as exc:
            raise GateAEvidenceError("GATE_A_FIXTURE_SELECTION_RECOMPUTE_FAILED") from exc
        if (
            reservation.selected_fixture_id != fixture_selection.selected_fixture_id
            or reservation.fixture_candidate_set_sha256 != fixture_selection.candidate_set_sha256
            or reservation.eligible_candidate_count != fixture_selection.eligible_candidate_count
        ):
            raise GateAEvidenceError("GATE_A_FIXTURE_SELECTION_LINEAGE_MISMATCH")
        fixture_ids = _fixture_aliases(fixture_selection.selected_fixture_id) | {
            str(row.fixture_id) for row in all_captures if row.fixture_id
        }
        fixture_identity_rows = list(
            session.scalars(
                select(MatchdayFixtureIdentityModel)
                .where(
                    (MatchdayFixtureIdentityModel.fixture_id.in_(fixture_ids))
                    | (
                        MatchdayFixtureIdentityModel.provider_fixture_id
                        == fixture_selection.selected_fixture_id
                    )
                )
                .order_by(MatchdayFixtureIdentityModel.fixture_id)
            )
        )
        all_lineup_rows = (
            list(
                session.scalars(
                    select(LineupConfirmedEventModel)
                    .where(LineupConfirmedEventModel.fixture_id.in_(fixture_ids))
                    .order_by(LineupConfirmedEventModel.event_id)
                )
            )
            if fixture_ids
            else []
        )
        all_dynamic_rows = (
            list(
                session.scalars(
                    select(DynamicPrematchEvaluationModel)
                    .where(DynamicPrematchEvaluationModel.fixture_id.in_(fixture_ids))
                    .order_by(DynamicPrematchEvaluationModel.evaluation_id)
                )
            )
            if fixture_ids
            else []
        )

    all_capture_ids = {row.capture_id for row in all_captures}
    all_pairs = [
        pair
        for pair in project_exact_eval_02b_pairs(engine).pairs
        if pair.identity.canonical_fixture_id in fixture_ids
        and pair.post_capture_id in all_capture_ids
    ]
    current_ids = {
        "provider_calls": [],
        "raw_payload": sorted(row.sha256 for row in all_raw_rows),
        "endpoint_capture": sorted(all_capture_ids),
        "lineup_event": sorted(row.event_id for row in all_lineup_rows),
        "dynamic_evaluation_v2": sorted(
            row.evaluation_id
            for row in all_dynamic_rows
            if row.payload.get("schema_version") == DYNAMIC_V2_SCHEMA
        ),
        "five_state_snapshot": sorted(
            row.evaluation_id
            for row in all_dynamic_rows
            if row.payload.get("schema_version") == DYNAMIC_V2_SCHEMA
            and _valid_five_state(row.payload.get("model_settlement_distribution"))
        ),
        "exact_pair": sorted(pair.identity_hash for pair in all_pairs),
        "bootstrap_seed_evidence": (
            [
                str(
                    eval_02b_bootstrap_seed(
                        [pair.identity_hash for pair in all_pairs],
                        contract_version=BOOTSTRAP_CONTRACT_VERSION,
                    )
                )
            ]
            if all_pairs
            else []
        ),
    }
    if any(
        not set(baseline[name]).issubset(current_ids[name])
        for name in BASELINE_KEYS - {"provider_calls", "bootstrap_seed_evidence"}
    ):
        raise GateAEvidenceError("GATE_A_EVIDENCE_BASELINE_AUTHORITY_REGRESSED")
    captures = [
        row for row in all_captures if row.capture_id not in set(baseline["endpoint_capture"])
    ]
    raw_rows = [
        row
        for row in all_raw_rows
        if row.sha256 not in set(baseline["raw_payload"])
        and row.inserted_at is not None
        and _utc(row.inserted_at) >= _utc(reservation.reserved_at)
        and _utc(row.inserted_at) <= _utc(reservation.finished_at)
    ]
    lineup_rows = [
        row
        for row in all_lineup_rows
        if row.event_id not in set(baseline["lineup_event"])
        and _utc(row.captured_at) >= _utc(reservation.reserved_at)
    ]
    dynamic_rows = [
        row
        for row in all_dynamic_rows
        if row.evaluation_id not in set(baseline["dynamic_evaluation_v2"])
        and _utc(row.evaluated_at) >= _utc(reservation.reserved_at)
    ]
    pairs = [
        pair
        for pair in all_pairs
        if pair.identity_hash not in set(baseline["exact_pair"])
        and pair.post_capture_at >= _utc(reservation.reserved_at)
    ]
    pair_evaluation_ids = {
        evaluation_id
        for pair in pairs
        for evaluation_id in (
            pair.identity.pre_evaluation_id,
            pair.identity.post_evaluation_id,
        )
    }
    with Session(engine) as session:
        pair_source_rows = (
            list(
                session.scalars(
                    select(DynamicPrematchEvaluationModel)
                    .where(DynamicPrematchEvaluationModel.evaluation_id.in_(pair_evaluation_ids))
                    .order_by(DynamicPrematchEvaluationModel.evaluation_id)
                )
            )
            if pair_evaluation_ids
            else []
        )
    pair_hashes = [pair.identity_hash for pair in pairs]
    bootstrap_seed = eval_02b_bootstrap_seed(
        pair_hashes,
        contract_version=BOOTSTRAP_CONTRACT_VERSION,
    )
    five_state_rows = [
        row
        for row in dynamic_rows
        if row.payload.get("schema_version") == DYNAMIC_V2_SCHEMA
        and _valid_five_state(row.payload.get("model_settlement_distribution"))
    ]
    deltas = {
        "provider_calls": len(provider_calls),
        "raw_payload": len(raw_rows),
        "endpoint_capture": len(captures),
        "lineup_event": len(lineup_rows),
        "dynamic_evaluation_v2": sum(
            row.payload.get("schema_version") == DYNAMIC_V2_SCHEMA for row in dynamic_rows
        ),
        "five_state_snapshot": len(five_state_rows),
        "exact_pair": len(pairs),
        "bootstrap_seed_evidence": int(bool(pair_hashes)),
    }
    return {
        "schema_version": GATE_A_EVIDENCE_SCHEMA,
        "serializer_version": SERIALIZER_VERSION,
        "binding": _binding(authorization),
        "artifact_counts": {
            name: {
                "before": len(baseline[name]),
                "after": len(baseline[name]) + delta,
                "delta": delta,
            }
            for name, delta in deltas.items()
        },
        "lineage": {
            **_authorization_authority(authorization, authorization_source),
            "reservation": {
                "lease_epoch": reservation.lease_epoch,
                "authorization_id": reservation.authorization_id,
                "task_key": reservation.task_key,
                "fixture_id": reservation.fixture_id,
                "competition_id": reservation.competition_id,
                "season": reservation.season,
                "provider_league_id": reservation.provider_league_id,
                "fixture_scope_mode": reservation.fixture_scope_mode,
                "kickoff_window_start_utc": _iso(reservation.kickoff_window_start_utc),
                "kickoff_window_end_utc": _iso(reservation.kickoff_window_end_utc),
                "selection_policy_version": reservation.selection_policy_version,
                "policy_config_hash": reservation.policy_config_hash,
                "selected_fixture_id": reservation.selected_fixture_id,
                "fixture_candidate_set_sha256": reservation.fixture_candidate_set_sha256,
                "fixture_discovery_capture_id": reservation.fixture_discovery_capture_id,
                "eligible_candidate_count": reservation.eligible_candidate_count,
                "fixture_selected_at": _iso(reservation.fixture_selected_at),
                "status": reservation.status,
                "reserved_at": _iso(reservation.reserved_at),
                "finished_at": _iso(reservation.finished_at),
                "provider_call_cap": reservation.provider_call_cap,
                "provider_calls_used": reservation.provider_calls_used,
                "evidence_baseline": baseline,
            },
            "fixture_selection": {
                "fixture_scope_mode": authorization.fixture_scope_mode,
                "kickoff_window_start_utc": _iso(authorization.kickoff_window_start_utc),
                "kickoff_window_end_utc": _iso(authorization.kickoff_window_end_utc),
                "selection_policy_version": authorization.selection_policy_version,
                "policy_config_hash": authorization.competition_policy_config_hash,
                "provider_league_id": authorization.provider_league_id,
                "discovery_endpoint_capture_id": discovery_capture.capture_id,
                "candidate_set_sha256": fixture_selection.candidate_set_sha256,
                "eligible_candidate_count": fixture_selection.eligible_candidate_count,
                "eligible_candidates": list(fixture_selection.candidates),
                "selected_fixture_id": fixture_selection.selected_fixture_id,
                "selected_at": _iso(reservation.fixture_selected_at),
                "reservation_selected_fixture_id": reservation.selected_fixture_id,
            },
            "task_audit": {
                "task_id": audit.task_id,
                "task_key": audit.key,
                "authorization_id": audit.gate_a_authorization_id,
                "lease_epoch": audit.gate_a_lease_epoch,
                "planned_at": _iso(audit.queued_at),
                "actual_execution_started_at": _iso(audit.started_at),
                "finished_at": _iso(audit.finished_at),
                "status": audit.status,
                "result": audit.result,
            },
            "provider_calls": [
                {
                    "lease_epoch": row.lease_epoch,
                    "ordinal": row.call_ordinal,
                    "endpoint": row.endpoint,
                    "state": row.state,
                }
                for row in provider_calls
            ],
            "raw_payload_rows": [
                {
                    "sha256": row.sha256,
                    "endpoint": row.endpoint,
                    "captured_at": _iso(row.captured_at),
                    "inserted_at": _iso(row.inserted_at),
                    "storage_uri": row.storage_uri,
                }
                for row in raw_rows
            ],
            "endpoint_capture_rows": [
                {
                    "capture_id": row.capture_id,
                    "endpoint": row.endpoint,
                    "fixture_id": row.fixture_id,
                    "request_task_key": row.request_task_key,
                    "raw_payload_sha256": row.raw_payload_sha256,
                    "provider_captured_at": _iso(row.provider_captured_at),
                }
                for row in captures
            ],
            "fixture_identity_rows": [
                {
                    "fixture_id": row.fixture_id,
                    "provider_fixture_id": row.provider_fixture_id,
                    "competition_id": row.competition_id,
                    "provider_league_id": row.provider_league_id,
                    "season": row.season,
                    "kickoff_utc": _iso(row.kickoff_utc),
                    "raw_payload_sha256": row.raw_payload_sha256,
                    "endpoint_capture_id": row.endpoint_capture_id,
                    "identity_hash": row.identity_hash,
                }
                for row in fixture_identity_rows
            ],
            "lineup_event_rows": [
                {
                    "event_id": row.event_id,
                    "fixture_id": row.fixture_id,
                    "captured_at": _iso(row.captured_at),
                    "source_capture_id": row.payload.get("source_capture_id"),
                    "raw_sha256": row.payload.get("raw_sha256"),
                }
                for row in lineup_rows
            ],
            "dynamic_evaluation_v2_rows": [
                {
                    "evaluation_id": row.evaluation_id,
                    "fixture_id": row.fixture_id,
                    "capture_id": row.capture_id,
                    "capture_at": _iso(row.capture_at),
                    "identity_hash": row.identity_hash,
                    "schema_version": row.payload.get("schema_version"),
                }
                for row in dynamic_rows
                if row.payload.get("schema_version") == DYNAMIC_V2_SCHEMA
            ],
            "five_state_snapshot_rows": [
                {
                    "evaluation_id": row.evaluation_id,
                    "distribution": row.payload["model_settlement_distribution"],
                    "distribution_sha256": canonical_sha256(
                        row.payload["model_settlement_distribution"],
                        domain=HashDomain.PREMATCH_READ_MODEL_DYNAMIC_EVALUATION,
                    ),
                }
                for row in five_state_rows
            ],
            "exact_pair_source_rows": [
                {
                    "evaluation_id": row.evaluation_id,
                    "fixture_id": row.fixture_id,
                    "provider_id": row.payload.get("provider"),
                    "bookmaker_id": row.payload.get("bookmaker_id"),
                    "market": row.market,
                    "selection": row.selection,
                    "exact_line": row.payload.get("exact_line"),
                    "capture_id": row.capture_id,
                    "capture_at": _iso(row.capture_at),
                    "schema_version": row.payload.get("schema_version"),
                }
                for row in pair_source_rows
            ],
        },
        "exact_pair_rows": [
            {
                "identity_input": pair.identity.as_dict(),
                "pair_identity_sha256": pair.identity_hash,
                "pre_capture_id": pair.pre_capture_id,
                "post_capture_id": pair.post_capture_id,
                "pre_capture_at": _iso(pair.pre_capture_at),
                "post_capture_at": _iso(pair.post_capture_at),
                "baseline_distribution": pair.baseline_distribution,
                "candidate_distribution": pair.candidate_distribution,
            }
            for pair in pairs
        ],
        "bootstrap_seed_evidence": {
            "contract_version": BOOTSTRAP_CONTRACT_VERSION,
            "validation_pair_identity_hashes": pair_hashes,
            "bootstrap_seed": bootstrap_seed,
        },
        "independent_oracle": _oracle_identity(),
    }


def _reservation_matches_authorization(
    reservation: GateARunReservationModel,
    authorization: GateARuntimeAuthorization,
) -> None:
    fields = (
        (reservation.task_key, authorization.task_key),
        (reservation.fixture_id, authorization.fixture_id),
        (reservation.provider_league_id, authorization.provider_league_id),
        (reservation.fixture_scope_mode, authorization.fixture_scope_mode),
        (_iso(reservation.kickoff_window_start_utc), _iso(authorization.kickoff_window_start_utc)),
        (_iso(reservation.kickoff_window_end_utc), _iso(authorization.kickoff_window_end_utc)),
        (reservation.selection_policy_version, authorization.selection_policy_version),
        (reservation.policy_config_hash, authorization.competition_policy_config_hash),
        (reservation.competition_id, authorization.competition_id),
        (reservation.season, authorization.season),
        (reservation.provider_call_cap, authorization.provider_call_cap),
        (reservation.exact_head, authorization.exact_head),
        (reservation.exact_tree, authorization.exact_tree),
        (reservation.execution_mode, authorization.execution_mode),
        (reservation.runtime_artifact_digest, authorization.runtime_artifact_digest),
        (
            reservation.complete_checkout_manifest_sha256,
            authorization.complete_checkout_manifest_sha256,
        ),
    )
    if any(actual != expected for actual, expected in fields):
        raise GateAError("GATE_A_RESERVATION_AUTHORIZATION_MISMATCH")


def _authorized_fixture_aliases(authorization: GateARuntimeAuthorization) -> set[str]:
    fixture_id = authorization.fixture_id
    if fixture_id is None:
        return set()
    return _fixture_aliases(fixture_id)


def _fixture_aliases(fixture_id: str) -> set[str]:
    if fixture_id.startswith("api_football:"):
        return {fixture_id, fixture_id.removeprefix("api_football:")}
    return {fixture_id, f"api_football:{fixture_id}"}


def _authorization_authority(
    authorization: GateARuntimeAuthorization,
    authorization_source: Path,
) -> dict[str, dict[str, str | int | None]]:
    common: dict[str, str | int | None] = {
        "source_path": str(authorization_source),
        "source_sha256": hashlib.sha256(authorization_source.read_bytes()).hexdigest(),
        "approval_mode": authorization.approval_mode,
    }
    if authorization.approval_mode == GATE_A_OWNER_APPROVAL_MODE:
        return {
            "owner_authorization": {
                **common,
                "owner_decision_issue": authorization.owner_decision_issue,
                "owner_decision_comment_id": authorization.owner_decision_comment_id,
            }
        }
    return {
        "signed_authorization": {
            **common,
            "approval_key_id": authorization.approval_key_id,
            "approval_public_key_sha256": authorization.approval_public_key_sha256,
            "approval_custody_status": authorization.approval_custody_status,
        }
    }


def _binding(authorization: GateARuntimeAuthorization) -> dict[str, str | int | None]:
    return {
        "authorization_id": authorization.authorization_id,
        "approval_mode": authorization.approval_mode,
        "owner_decision_issue": authorization.owner_decision_issue,
        "owner_decision_comment_id": authorization.owner_decision_comment_id,
        "task_key": authorization.task_key,
        "fixture_id": authorization.fixture_id,
        "provider_league_id": authorization.provider_league_id,
        "fixture_scope_mode": authorization.fixture_scope_mode,
        "kickoff_window_start_utc": _iso(authorization.kickoff_window_start_utc),
        "kickoff_window_end_utc": _iso(authorization.kickoff_window_end_utc),
        "selection_policy_version": authorization.selection_policy_version,
        "policy_config_hash": authorization.competition_policy_config_hash,
        "competition": authorization.competition_id,
        "policy_season": authorization.season,
        "exact_head": authorization.exact_head,
        "exact_tree": authorization.exact_tree,
        "execution_mode": authorization.execution_mode,
        "runtime_artifact_digest": authorization.runtime_artifact_digest,
        "complete_checkout_manifest_sha256": authorization.complete_checkout_manifest_sha256,
        "serializer_version": SERIALIZER_VERSION,
    }


def _oracle_identity() -> dict[str, str]:
    root = Path(__file__).resolve().parents[3]
    source = root / "oracle/canonical_serialization_oracle.py"
    return {
        "source_path": "oracle/canonical_serialization_oracle.py",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "transport_path": "scripts/invoke_independent_canonical_oracle.py",
    }


def _valid_five_state(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != set(FIVE_STATE_KEYS):
        return False
    try:
        probabilities = [float(value[key]) for key in FIVE_STATE_KEYS]
    except (TypeError, ValueError):
        return False
    return (
        all(number >= 0 and number < float("inf") for number in probabilities)
        and abs(sum(probabilities) - 1.0) <= 1e-9
    )


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else _utc(value).isoformat().replace("+00:00", "Z")
