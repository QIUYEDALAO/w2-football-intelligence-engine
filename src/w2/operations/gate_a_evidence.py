from __future__ import annotations

import ast
import hashlib
import hmac
import json
import math
import re
import subprocess
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from w2.domain.canonical_serialization import (
    HashDomain,
    canonical_sha256,
    eval_02b_bootstrap_seed,
)
from w2.operations.gate_a import (
    GATE_A_EXACT_FIXTURE_SCOPE,
    GATE_A_OWNER_APPROVAL_MODE,
    GATE_A_SELECTION_POLICY_VERSION,
    GATE_A_WINDOW_FIXTURE_SCOPE,
    GateARuntimeAuthorization,
)

GATE_A_EVIDENCE_SCHEMA = "w2.gate-a-admission-evidence.v6"
SERIALIZER_VERSION = "w2.canonical-json.v2"
ROOT = Path(__file__).resolve().parents[3]
ORACLE_SOURCE = ROOT / "oracle/canonical_serialization_oracle.py"
ORACLE_TRANSPORT = ROOT / "scripts/invoke_independent_canonical_oracle.py"
REQUIRED_ARTIFACTS = {
    "provider_calls": "provider_calls",
    "raw_payload": "raw_payload_rows",
    "endpoint_capture": "endpoint_capture_rows",
    "lineup_event": "lineup_event_rows",
    "dynamic_evaluation_v2": "dynamic_evaluation_v2_rows",
    "five_state_snapshot": "five_state_snapshot_rows",
}
REQUIRED_BINDING_FIELDS = {
    "authorization_id",
    "approval_mode",
    "owner_decision_issue",
    "owner_decision_comment_id",
    "task_key",
    "fixture_id",
    "provider_league_id",
    "fixture_scope_mode",
    "kickoff_window_start_utc",
    "kickoff_window_end_utc",
    "selection_policy_version",
    "policy_config_hash",
    "competition",
    "policy_season",
    "exact_head",
    "exact_tree",
    "execution_mode",
    "runtime_artifact_digest",
    "complete_checkout_manifest_sha256",
    "serializer_version",
}
FIVE_STATE_KEYS = ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")


class GateAEvidenceError(RuntimeError):
    pass


def validate_gate_a_evidence(
    payload: Mapping[str, Any],
    *,
    authorization: GateARuntimeAuthorization,
    authorization_source_sha256: str,
) -> None:
    if payload.get("schema_version") != GATE_A_EVIDENCE_SCHEMA:
        raise GateAEvidenceError("GATE_A_EVIDENCE_SCHEMA_INVALID")
    if payload.get("serializer_version") != SERIALIZER_VERSION:
        raise GateAEvidenceError("SERIALIZER_VERSION_MISSING")
    if _contains_non_finite(payload):
        raise GateAEvidenceError("NAN_OR_INFINITY")
    _validate_binding(payload.get("binding"), authorization=authorization)
    lineage = _mapping(payload.get("lineage"), "LINEAGE_INVALID")
    _validate_authority_lineage(
        lineage,
        authorization=authorization,
        authorization_source_sha256=authorization_source_sha256,
    )
    pair_rows = _list_of_mappings(payload.get("exact_pair_rows"), "EXACT_PAIR_EVIDENCE_INVALID")
    production_hashes = _production_pair_hashes(pair_rows, lineage=lineage)
    production_seed = _production_bootstrap(
        payload.get("bootstrap_seed_evidence"), production_hashes
    )
    _validate_producer_counts(
        payload.get("artifact_counts"), lineage=lineage, pair_count=len(pair_rows)
    )
    _validate_content(lineage, pair_rows=pair_rows)
    independent = _independent_recompute(
        payload.get("independent_oracle"),
        pair_rows=pair_rows,
        contract_version=str(
            _mapping(payload["bootstrap_seed_evidence"], "BOOTSTRAP_SEED_EVIDENCE_INVALID")[
                "contract_version"
            ]
        ),
    )
    if independent["pair_identity_sha256"] != production_hashes:
        raise GateAEvidenceError("INDEPENDENT_PAIR_IDENTITY_MISMATCH")
    if independent["bootstrap_seed"] != production_seed:
        raise GateAEvidenceError("INDEPENDENT_BOOTSTRAP_SEED_MISMATCH")
    if independent.get("production_imported") is not False:
        raise GateAEvidenceError("INDEPENDENT_ORACLE_IMPORTED_PRODUCTION")


def _validate_binding(value: Any, *, authorization: GateARuntimeAuthorization) -> None:
    binding = _mapping(value, "EVIDENCE_BINDING_INVALID")
    if set(binding) != REQUIRED_BINDING_FIELDS:
        raise GateAEvidenceError("EVIDENCE_BINDING_INVALID")
    expected: dict[str, str | int | None] = {
        "authorization_id": authorization.authorization_id,
        "approval_mode": authorization.approval_mode,
        "owner_decision_issue": authorization.owner_decision_issue,
        "owner_decision_comment_id": authorization.owner_decision_comment_id,
        "task_key": authorization.task_key,
        "fixture_id": authorization.fixture_id,
        "provider_league_id": authorization.provider_league_id,
        "fixture_scope_mode": authorization.fixture_scope_mode,
        "kickoff_window_start_utc": _iso_or_none(authorization.kickoff_window_start_utc),
        "kickoff_window_end_utc": _iso_or_none(authorization.kickoff_window_end_utc),
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
    for field, expected_value in expected.items():
        actual = binding.get(field)
        if actual is None or expected_value is None:
            if actual != expected_value:
                raise GateAEvidenceError("EVIDENCE_BINDING_MISMATCH")
        elif not hmac.compare_digest(str(actual), str(expected_value)):
            raise GateAEvidenceError("EVIDENCE_BINDING_MISMATCH")
    if authorization.execution_mode == "IMMUTABLE_IMAGE":
        if binding["runtime_artifact_digest"] is None:
            raise GateAEvidenceError("EVIDENCE_RUNTIME_IDENTITY_INVALID")
    elif binding["complete_checkout_manifest_sha256"] is None:
        raise GateAEvidenceError("EVIDENCE_RUNTIME_IDENTITY_INVALID")


def _validate_authority_lineage(
    lineage: Mapping[str, Any],
    *,
    authorization: GateARuntimeAuthorization,
    authorization_source_sha256: str,
) -> None:
    if authorization.approval_mode == GATE_A_OWNER_APPROVAL_MODE:
        authority = _mapping(
            lineage.get("owner_authorization"), "OWNER_AUTHORIZATION_LINEAGE_INVALID"
        )
        authority_mismatch = (
            "signed_authorization" in lineage
            or authority.get("approval_mode") != authorization.approval_mode
            or authority.get("owner_decision_issue") != authorization.owner_decision_issue
            or authority.get("owner_decision_comment_id")
            != authorization.owner_decision_comment_id
        )
    else:
        authority = _mapping(
            lineage.get("signed_authorization"), "SIGNED_AUTHORIZATION_LINEAGE_INVALID"
        )
        authority_mismatch = (
            authority.get("approval_mode") != authorization.approval_mode
            or authority.get("approval_key_id") != authorization.approval_key_id
            or authority.get("approval_public_key_sha256")
            != authorization.approval_public_key_sha256
            or authority.get("approval_custody_status") != "INDEPENDENT_SIGNER_CONFIRMED"
        )
    reservation = _mapping(lineage.get("reservation"), "RESERVATION_LINEAGE_INVALID")
    selection = _mapping(lineage.get("fixture_selection"), "FIXTURE_SELECTION_LINEAGE_INVALID")
    audit = _mapping(lineage.get("task_audit"), "TASK_AUDIT_LINEAGE_INVALID")
    if (
        authority_mismatch
        or authority.get("source_sha256") != authorization_source_sha256
        or reservation.get("authorization_id") != authorization.authorization_id
        or reservation.get("task_key") != authorization.task_key
        or reservation.get("fixture_id") != authorization.fixture_id
        or reservation.get("provider_league_id") != authorization.provider_league_id
        or reservation.get("fixture_scope_mode") != authorization.fixture_scope_mode
        or reservation.get("kickoff_window_start_utc")
        != _iso_or_none(authorization.kickoff_window_start_utc)
        or reservation.get("kickoff_window_end_utc")
        != _iso_or_none(authorization.kickoff_window_end_utc)
        or reservation.get("selection_policy_version") != authorization.selection_policy_version
        or reservation.get("policy_config_hash") != authorization.competition_policy_config_hash
        or reservation.get("status") != "COMPLETED"
        or audit.get("task_key") != authorization.task_key
        or audit.get("authorization_id") != authorization.authorization_id
        or audit.get("lease_epoch") != reservation.get("lease_epoch")
        or audit.get("status") != "COMPLETED"
    ):
        raise GateAEvidenceError("AUTHORITY_LINEAGE_MISMATCH")
    selected_fixture_id = _validate_fixture_selection(
        selection,
        reservation=reservation,
        authorization=authorization,
    )
    provider_calls = _list_of_mappings(
        lineage.get("provider_calls"), "PROVIDER_CALL_LINEAGE_INVALID"
    )
    if any(row.get("state") != "RESPONSE_RECEIVED" for row in provider_calls):
        raise GateAEvidenceError("PROVIDER_CALL_OUTCOME_NOT_RECEIVED")
    lease_epoch = reservation.get("lease_epoch")
    ordinals = [row.get("ordinal") for row in provider_calls]
    provider_calls_used = reservation.get("provider_calls_used")
    provider_call_cap = reservation.get("provider_call_cap")
    request_count = _mapping(audit.get("result"), "AUTHORITY_LINEAGE_MISMATCH").get("request_count")
    if (
        isinstance(provider_calls_used, bool)
        or not isinstance(provider_calls_used, int)
        or isinstance(provider_call_cap, bool)
        or not isinstance(provider_call_cap, int)
        or isinstance(request_count, bool)
        or not isinstance(request_count, int)
        or len(provider_calls) != provider_calls_used
        or provider_calls_used != request_count
        or provider_calls_used > provider_call_cap
    ):
        raise GateAEvidenceError("PROVIDER_CALL_COUNT_MISMATCH")
    if ordinals != list(range(1, len(provider_calls) + 1)):
        raise GateAEvidenceError("PROVIDER_CALL_ORDINALS_NOT_CONTIGUOUS")
    if any(row.get("lease_epoch") != lease_epoch for row in provider_calls):
        raise GateAEvidenceError("PROVIDER_CALL_LEASE_MISMATCH")
    if any(row.get("endpoint") not in authorization.allowed_endpoints for row in provider_calls):
        raise GateAEvidenceError("PROVIDER_ENDPOINT_OUTSIDE_AUTHORIZED_SCOPE")
    if [row.get("endpoint") for row in provider_calls] != [
        "status",
        "fixtures",
        "odds",
        "lineups",
        "odds",
    ]:
        raise GateAEvidenceError("STAGED_PROVIDER_SEQUENCE_INVALID")
    fixture_aliases = _fixture_aliases(selected_fixture_id)
    captures = _list_of_mappings(
        lineage.get("endpoint_capture_rows"), "ENDPOINT_CAPTURE_LINEAGE_INVALID"
    )
    discovery_capture_id = selection.get("discovery_endpoint_capture_id")
    for row in captures:
        endpoint = row.get("endpoint")
        fixture_id = row.get("fixture_id")
        if endpoint == "fixtures":
            if row.get("capture_id") != discovery_capture_id or fixture_id is not None:
                raise GateAEvidenceError("GATE_A_FIXTURE_DISCOVERY_LINEAGE_INVALID")
        elif endpoint == "status":
            if fixture_id is not None:
                raise GateAEvidenceError("GATE_A_FIXTURE_SCOPE_MISMATCH")
        elif endpoint in {"odds", "lineups"}:
            if fixture_id not in fixture_aliases:
                raise GateAEvidenceError("GATE_A_FIXTURE_SCOPE_MISMATCH")
        else:
            raise GateAEvidenceError("PROVIDER_ENDPOINT_OUTSIDE_AUTHORIZED_SCOPE")
    source_sha = authority.get("source_sha256")
    if (
        not isinstance(source_sha, str)
        or re.fullmatch(r"[0-9a-f]{64}", source_sha) is None
        or not isinstance(audit.get("result"), Mapping)
    ):
        raise GateAEvidenceError("AUTHORITY_LINEAGE_MISMATCH")


def _validate_fixture_selection(
    selection: Mapping[str, Any],
    *,
    reservation: Mapping[str, Any],
    authorization: GateARuntimeAuthorization,
) -> str:
    candidates = _list_of_mappings(
        selection.get("eligible_candidates"), "FIXTURE_SELECTION_LINEAGE_INVALID"
    )
    selected = selection.get("selected_fixture_id")
    candidate_hash = selection.get("candidate_set_sha256")
    if (
        selection.get("fixture_scope_mode") != authorization.fixture_scope_mode
        or selection.get("kickoff_window_start_utc")
        != _iso_or_none(authorization.kickoff_window_start_utc)
        or selection.get("kickoff_window_end_utc")
        != _iso_or_none(authorization.kickoff_window_end_utc)
        or selection.get("selection_policy_version") != GATE_A_SELECTION_POLICY_VERSION
        or selection.get("policy_config_hash") != authorization.competition_policy_config_hash
        or selection.get("provider_league_id") != authorization.provider_league_id
        or not isinstance(selected, str)
        or not selected.isascii()
        or not selected.isdigit()
        or int(selected) <= 0
        or selection.get("reservation_selected_fixture_id") != selected
        or reservation.get("selected_fixture_id") != selected
        or reservation.get("fixture_candidate_set_sha256") != candidate_hash
        or reservation.get("fixture_discovery_capture_id")
        != selection.get("discovery_endpoint_capture_id")
        or reservation.get("eligible_candidate_count") != len(candidates)
        or selection.get("eligible_candidate_count") != len(candidates)
        or reservation.get("fixture_selected_at") != selection.get("selected_at")
        or not candidates
        or candidates[0].get("fixture_id") != selected
    ):
        raise GateAEvidenceError("FIXTURE_SELECTION_LINEAGE_MISMATCH")
    for candidate in candidates:
        candidate_fixture_id = candidate.get("fixture_id")
        if (
            not isinstance(candidate_fixture_id, str)
            or not candidate_fixture_id.isascii()
            or not candidate_fixture_id.isdigit()
            or int(candidate_fixture_id) <= 0
        ):
            raise GateAEvidenceError("FIXTURE_SELECTION_LINEAGE_INVALID")
    if candidate_hash != canonical_sha256(candidates, domain=HashDomain.FUTURE_REFRESH_EVIDENCE):
        raise GateAEvidenceError("FIXTURE_SELECTION_LINEAGE_MISMATCH")
    ordered = sorted(
        candidates,
        key=lambda item: (str(item.get("kickoff_utc") or ""), int(str(item["fixture_id"]))),
    )
    if candidates != ordered:
        raise GateAEvidenceError("FIXTURE_SELECTION_ORDER_INVALID")
    if authorization.fixture_scope_mode == GATE_A_EXACT_FIXTURE_SCOPE:
        if selected != authorization.fixture_id:
            raise GateAEvidenceError("GATE_A_FIXTURE_SCOPE_MISMATCH")
    elif authorization.fixture_scope_mode == GATE_A_WINDOW_FIXTURE_SCOPE:
        assert authorization.kickoff_window_start_utc is not None
        assert authorization.kickoff_window_end_utc is not None
        for candidate in candidates:
            kickoff = _parse_iso(candidate.get("kickoff_utc"), "FIXTURE_SELECTION_LINEAGE_INVALID")
            if (
                candidate.get("provider_league_id") != authorization.provider_league_id
                or candidate.get("season") != authorization.season
                or not authorization.kickoff_window_start_utc
                <= kickoff
                <= authorization.kickoff_window_end_utc
            ):
                raise GateAEvidenceError("GATE_A_FIXTURE_SCOPE_MISMATCH")
    else:
        raise GateAEvidenceError("GATE_A_FIXTURE_SCOPE_MISMATCH")
    selected_at = _parse_iso(selection.get("selected_at"), "FIXTURE_SELECTION_LINEAGE_INVALID")
    if not (
        _parse_iso(reservation.get("reserved_at"), "FIXTURE_SELECTION_LINEAGE_INVALID")
        <= selected_at
        <= _parse_iso(reservation.get("finished_at"), "FIXTURE_SELECTION_LINEAGE_INVALID")
    ):
        raise GateAEvidenceError("FIXTURE_SELECTION_TIME_INVALID")
    return selected


def _production_pair_hashes(
    rows: list[Mapping[str, Any]],
    *,
    lineage: Mapping[str, Any],
) -> list[str]:
    source_rows = _list_of_mappings(
        lineage.get("exact_pair_source_rows"), "EXACT_PAIR_SOURCE_LINEAGE_INVALID"
    )
    source_by_id = {str(row.get("evaluation_id")): row for row in source_rows}
    hashes: list[str] = []
    for row in rows:
        identity = _mapping(row.get("identity_input"), "EXACT_PAIR_EVIDENCE_INVALID")
        if set(identity) != {
            "canonical_fixture_id",
            "competition_id",
            "season_id",
            "provider_id",
            "bookmaker_id",
            "market",
            "selection",
            "exact_line",
            "pre_evaluation_id",
            "post_evaluation_id",
        }:
            raise GateAEvidenceError("EXACT_PAIR_IDENTITY_INCOMPLETE")
        claimed = row.get("pair_identity_sha256")
        actual = canonical_sha256(identity, domain=HashDomain.EVAL_02B_PAIR_IDENTITY)
        if not isinstance(claimed, str) or not hmac.compare_digest(actual, claimed):
            raise GateAEvidenceError("PAIR_IDENTITY_RECOMPUTE_MISMATCH")
        for prefix in ("pre", "post"):
            source = source_by_id.get(str(identity[f"{prefix}_evaluation_id"]))
            if (
                source is None
                or source.get("schema_version") != "w2.dynamic_quote_evaluation.v2"
                or source.get("fixture_id") != identity["canonical_fixture_id"]
                or source.get("capture_id") != row.get(f"{prefix}_capture_id")
                or source.get("capture_at") != row.get(f"{prefix}_capture_at")
                or source.get("market") != identity["market"]
                or source.get("selection") != identity["selection"]
                or source.get("bookmaker_id") != identity["bookmaker_id"]
                or source.get("provider_id") != identity["provider_id"]
                or source.get("exact_line") != identity["exact_line"]
            ):
                raise GateAEvidenceError("EXACT_PAIR_SOURCE_IDENTITY_MISMATCH")
        hashes.append(actual)
    return hashes


def _production_bootstrap(value: Any, hashes: list[str]) -> int:
    evidence = _mapping(value, "BOOTSTRAP_SEED_EVIDENCE_INVALID")
    if (
        set(evidence)
        != {
            "contract_version",
            "validation_pair_identity_hashes",
            "bootstrap_seed",
        }
        or evidence.get("validation_pair_identity_hashes") != hashes
    ):
        raise GateAEvidenceError("BOOTSTRAP_SEED_EVIDENCE_INVALID")
    actual = eval_02b_bootstrap_seed(hashes, contract_version=str(evidence["contract_version"]))
    if evidence.get("bootstrap_seed") != actual:
        raise GateAEvidenceError("BOOTSTRAP_SEED_RECOMPUTE_MISMATCH")
    return actual


def _validate_content(lineage: Mapping[str, Any], *, pair_rows: list[Mapping[str, Any]]) -> None:
    raw_rows = _list_of_mappings(lineage.get("raw_payload_rows"), "RAW_PAYLOAD_LINEAGE_INVALID")
    captures = _list_of_mappings(
        lineage.get("endpoint_capture_rows"), "ENDPOINT_CAPTURE_LINEAGE_INVALID"
    )
    raw_hashes = {row.get("sha256") for row in raw_rows}
    reservation = _mapping(lineage.get("reservation"), "RESERVATION_LINEAGE_INVALID")
    reserved_at = _parse_iso(reservation.get("reserved_at"), "RAW_PAYLOAD_INSERTION_INVALID")
    finished_at = _parse_iso(reservation.get("finished_at"), "RAW_PAYLOAD_INSERTION_INVALID")
    if any(
        not reserved_at
        <= _parse_iso(row.get("inserted_at"), "RAW_PAYLOAD_INSERTION_INVALID")
        <= finished_at
        for row in raw_rows
    ):
        raise GateAEvidenceError("RAW_PAYLOAD_INSERTION_INVALID")
    if any(row.get("raw_payload_sha256") not in raw_hashes for row in captures):
        raise GateAEvidenceError("RAW_ENDPOINT_LINEAGE_MISMATCH")
    capture_by_id = {row.get("capture_id"): row for row in captures}
    selected = str(
        _mapping(lineage.get("fixture_selection"), "FIXTURE_SELECTION_LINEAGE_INVALID").get(
            "selected_fixture_id"
        )
        or ""
    )
    aliases = _fixture_aliases(selected)
    fixture_identities = _list_of_mappings(
        lineage.get("fixture_identity_rows"), "FIXTURE_IDENTITY_LINEAGE_INVALID"
    )
    if not fixture_identities:
        raise GateAEvidenceError("FIXTURE_IDENTITY_LINEAGE_INVALID")
    selection = _mapping(lineage.get("fixture_selection"), "FIXTURE_SELECTION_LINEAGE_INVALID")
    discovery_capture_id = selection.get("discovery_endpoint_capture_id")
    selected_candidate = next(
        (
            candidate
            for candidate in _list_of_mappings(
                selection.get("eligible_candidates"), "FIXTURE_SELECTION_LINEAGE_INVALID"
            )
            if candidate.get("fixture_id") == selected
        ),
        None,
    )
    for row in fixture_identities:
        if (
            selected_candidate is None
            or row.get("fixture_id") not in aliases
            or row.get("provider_fixture_id") != selected
            or row.get("competition_id")
            != _mapping(lineage.get("reservation"), "RESERVATION_LINEAGE_INVALID").get(
                "competition_id"
            )
            or row.get("provider_league_id") != selection.get("provider_league_id")
            or row.get("season")
            != _mapping(lineage.get("reservation"), "RESERVATION_LINEAGE_INVALID").get("season")
            or row.get("kickoff_utc") != selected_candidate.get("kickoff_utc")
            or row.get("endpoint_capture_id") != discovery_capture_id
            or row.get("raw_payload_sha256") not in raw_hashes
        ):
            raise GateAEvidenceError("FIXTURE_IDENTITY_LINEAGE_INVALID")
    lineup_rows = _list_of_mappings(
        lineage.get("lineup_event_rows"), "LINEUP_EVENT_LINEAGE_INVALID"
    )
    for row in lineup_rows:
        source = capture_by_id.get(row.get("source_capture_id"))
        if (
            source is None
            or source.get("raw_payload_sha256") != row.get("raw_sha256")
            or row.get("fixture_id") not in aliases
        ):
            raise GateAEvidenceError("LINEUP_CAPTURE_LINEAGE_MISMATCH")
    dynamics = _list_of_mappings(
        lineage.get("dynamic_evaluation_v2_rows"), "DYNAMIC_EVALUATION_LINEAGE_INVALID"
    )
    if any(
        row.get("schema_version") != "w2.dynamic_quote_evaluation.v2"
        or row.get("capture_id") not in capture_by_id
        or row.get("fixture_id") not in aliases
        for row in dynamics
    ):
        raise GateAEvidenceError("DYNAMIC_EVALUATION_V2_REQUIRED")
    five_rows = _list_of_mappings(
        lineage.get("five_state_snapshot_rows"), "FIVE_STATE_LINEAGE_INVALID"
    )
    dynamic_ids = {row.get("evaluation_id") for row in dynamics}
    for row in five_rows:
        if row.get("evaluation_id") not in dynamic_ids:
            raise GateAEvidenceError("FIVE_STATE_DYNAMIC_LINEAGE_MISMATCH")
        _validate_distribution(row.get("distribution"))
        if row.get("distribution_sha256") != canonical_sha256(
            row["distribution"], domain=HashDomain.PREMATCH_READ_MODEL_DYNAMIC_EVALUATION
        ):
            raise GateAEvidenceError("FIVE_STATE_LINEAGE_HASH_MISMATCH")
    for pair in pair_rows:
        identity = _mapping(pair.get("identity_input"), "EXACT_PAIR_EVIDENCE_INVALID")
        if identity.get("canonical_fixture_id") not in aliases:
            raise GateAEvidenceError("GATE_A_FIXTURE_SCOPE_MISMATCH")
        _validate_distribution(pair.get("baseline_distribution"))
        _validate_distribution(pair.get("candidate_distribution"))


def _validate_distribution(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != set(FIVE_STATE_KEYS):
        raise GateAEvidenceError("FIVE_STATE_KEYS_INVALID")
    numbers: list[float] = []
    for key in FIVE_STATE_KEYS:
        item = value[key]
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise GateAEvidenceError("FIVE_STATE_PROBABILITY_INVALID")
        number = float(item)
        if not math.isfinite(number) or number < 0:
            raise GateAEvidenceError("FIVE_STATE_PROBABILITY_INVALID")
        numbers.append(number)
    if abs(sum(numbers) - 1.0) > 1e-9:
        raise GateAEvidenceError("FIVE_STATE_PROBABILITY_SUM_INVALID")


def _validate_producer_counts(
    value: Any,
    *,
    lineage: Mapping[str, Any],
    pair_count: int,
) -> None:
    counts = _mapping(value, "ARTIFACT_COUNTS_INVALID")
    if set(counts) != set(REQUIRED_ARTIFACTS) | {"exact_pair", "bootstrap_seed_evidence"}:
        raise GateAEvidenceError("ARTIFACT_COUNTS_INVALID")
    derived = {
        name: len(_list_of_mappings(lineage.get(lineage_key), "ARTIFACT_LINEAGE_INVALID"))
        for name, lineage_key in REQUIRED_ARTIFACTS.items()
    }
    derived.update(exact_pair=pair_count, bootstrap_seed_evidence=int(pair_count > 0))
    reservation = _mapping(lineage.get("reservation"), "RESERVATION_LINEAGE_INVALID")
    baseline = _mapping(reservation.get("evidence_baseline"), "GATE_A_EVIDENCE_BASELINE_INVALID")
    if set(baseline) != set(derived) or any(
        not isinstance(values, list) for values in baseline.values()
    ):
        raise GateAEvidenceError("GATE_A_EVIDENCE_BASELINE_INVALID")
    for name, expected_delta in derived.items():
        count = _mapping(counts.get(name), "ARTIFACT_COUNTS_INVALID")
        before = len(baseline[name])
        if set(count) != {"before", "after", "delta"}:
            raise GateAEvidenceError("ARTIFACT_COUNTS_INVALID")
        if (
            count.get("before") != before
            or count.get("after") != before + expected_delta
            or count.get("delta") != expected_delta
        ):
            raise GateAEvidenceError("CALLER_ASSERTED_ARTIFACT_COUNT_REJECTED")
        if expected_delta <= 0:
            raise GateAEvidenceError("ANY_REQUIRED_ARTIFACT_DELTA_ZERO")


def _independent_recompute(
    value: Any,
    *,
    pair_rows: list[Mapping[str, Any]],
    contract_version: str,
) -> dict[str, Any]:
    identity = _mapping(value, "INDEPENDENT_ORACLE_IDENTITY_INVALID")
    if identity.get("source_path") != "oracle/canonical_serialization_oracle.py":
        raise GateAEvidenceError("INDEPENDENT_ORACLE_IDENTITY_INVALID")
    source_hash = _file_sha256(ORACLE_SOURCE)
    if identity.get("source_sha256") != source_hash:
        raise GateAEvidenceError("INDEPENDENT_ORACLE_SOURCE_SHA_MISMATCH")
    for source in (ORACLE_SOURCE, ORACLE_TRANSPORT):
        if _imports_w2(source.read_text(encoding="utf-8")):
            raise GateAEvidenceError("INDEPENDENT_ORACLE_IMPORTS_PRODUCTION")
    command = [
        sys.executable,
        "-I",
        str(ORACLE_TRANSPORT),
        "--contract-version",
        contract_version,
    ]
    for row in pair_rows:
        identity = row["identity_input"]
        assert isinstance(identity, Mapping)
        command.extend(
            [
                "--pair",
                _transport_arg(identity["canonical_fixture_id"]),
                _transport_arg(identity["competition_id"]),
                _transport_arg(identity["season_id"]),
                _transport_arg(identity["provider_id"]),
                _transport_arg(identity["bookmaker_id"]),
                _transport_arg(identity["market"]),
                _transport_arg(identity["selection"]),
                _transport_arg(float(identity["exact_line"]).hex()),
                _transport_arg(identity["pre_evaluation_id"]),
                _transport_arg(identity["post_evaluation_id"]),
            ]
        )
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=True,
            cwd=ROOT,
            env={"PATH": str(Path(sys.executable).parent)},
            text=True,
        )
        result = json.loads(completed.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise GateAEvidenceError("INDEPENDENT_ORACLE_EXECUTION_FAILED") from exc
    if not isinstance(result, dict):
        raise GateAEvidenceError("INDEPENDENT_ORACLE_OUTPUT_INVALID")
    return result


def _imports_w2(source: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name == "w2" or alias.name.startswith("w2.") for alias in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "w2" or module.startswith("w2."):
                return True
    return False


def _transport_arg(value: Any) -> str:
    return str(value).encode("utf-8").hex()


def _mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GateAEvidenceError(code)
    return value


def _parse_iso(value: Any, code: str) -> datetime:
    if not isinstance(value, str):
        raise GateAEvidenceError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GateAEvidenceError(code) from exc
    if parsed.tzinfo is None:
        raise GateAEvidenceError(code)
    return parsed.astimezone(UTC)


def _list_of_mappings(value: Any, code: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, Mapping) for row in value):
        raise GateAEvidenceError(code)
    return value


def _contains_non_finite(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, Mapping):
        return any(_contains_non_finite(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_non_finite(item) for item in value)
    return False


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_aliases(fixture_id: str) -> set[str]:
    if fixture_id.startswith("api_football:"):
        return {fixture_id, fixture_id.removeprefix("api_football:")}
    return {fixture_id, f"api_football:{fixture_id}"}


def _iso_or_none(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(UTC).isoformat().replace("+00:00", "Z")
