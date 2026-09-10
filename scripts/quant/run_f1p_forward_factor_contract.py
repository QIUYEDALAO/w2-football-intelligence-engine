"""F1P runner: publish the forward factor contract and exercise it offline.

Deterministic and entirely local. It writes the machine-readable schema
contract, builds a small reference ledger from fixed synthetic fixtures to
demonstrate the rules, and records the terminal state.

It fits nothing, produces no weight and no direction, and reads no production
data. The reference ledger is a worked example of the contract, not evidence
about any real match.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

_CONTRACT_PATH = Path(__file__).resolve().parent / "f1p_forward_factor_contract.py"
_MODULE_NAME = "w2_f1p_forward_factor_contract"
_spec = importlib.util.spec_from_file_location(_MODULE_NAME, _CONTRACT_PATH)
assert _spec is not None and _spec.loader is not None
contract = importlib.util.module_from_spec(_spec)
# registered before exec: dataclass resolves annotations through sys.modules
sys.modules[_MODULE_NAME] = contract
_spec.loader.exec_module(contract)

TASK_ID = "W2_AH_FACTOR_ACCURACY_F1P_FORWARD_CONTRACT_20260910"
PARENT_COMMIT = "71cffa8d4ab8e7a7d4a779cc91951c97f594a261"
LEDGER_NAME = "F1P_REFERENCE_LEDGER.jsonl"
POST_EVENT_NAME = "F1P_REFERENCE_POST_EVENT.jsonl"

# Synthetic and fixed, so two runs are byte-identical. These are not real
# matches and carry no result; the ids are obviously synthetic on purpose.
_FIXTURE_EVALUATION = "dqe-" + "1" * 64
_FIXTURE_ATTEMPT = "att-" + "2" * 60
_FIXTURE_CAPTURE_SHA = "3" * 64
_EVIDENCE = "2026-10-01T17:30:00+00:00"
_EVALUATED = "2026-10-01T18:30:00+00:00"
_CREATED = "2026-10-01T18:30:01+00:00"

REFERENCE_ROWS: tuple[dict[str, Any], ...] = (
    {"factor_id": "F3_REST_FITNESS", "factor_status": contract.PARTICIPATED,
     "participated": True, "applied_weight": "0.10", "signed_score": "0.25",
     "factor_inputs": {"home_rest_days": "5.0", "away_rest_days": "4.0"}},
    {"factor_id": "F9_TRUE_XG", "factor_status": contract.PARTICIPATED,
     "participated": True, "applied_weight": "0.10", "signed_score": "-0.12",
     "factor_inputs": {"home_xg_for": "1.42", "away_xg_for": "1.58"}},
    # An absence stays an absence: no score, and no weight invented for it.
    {"factor_id": "F5_RECENT_AH_COVER", "factor_status": contract.INSUFFICIENT_DATA,
     "participated": False, "applied_weight": "0.05", "signed_score": None,
     "factor_inputs": {"observed_matches": "2", "required_matches": "5"}},
    {"factor_id": "F6_H2H", "factor_status": contract.SOURCE_UNAVAILABLE,
     "participated": False, "applied_weight": "0.05", "signed_score": None,
     "factor_inputs": {"meetings_found": "0"}},
)


def build_record(row: dict[str, Any]) -> Any:
    return contract.ForwardFactorObservation(
        evaluation_id=_FIXTURE_EVALUATION,
        attempt_id=_FIXTURE_ATTEMPT,
        fixture_id="9000001",
        factor_id=row["factor_id"],
        factor_version="v1",
        factor_status=row["factor_status"],
        participated=row["participated"],
        applied_weight=row["applied_weight"],
        factor_inputs=row["factor_inputs"],
        evidence_time_utc=_EVIDENCE,
        evaluated_at_utc=_EVALUATED,
        created_at_utc=_CREATED,
        source_capture_id="reference-capture-1",
        source_capture_sha256=_FIXTURE_CAPTURE_SHA,
        source_version="w2.analysis_card.reference.v1",
        signed_score=row["signed_score"],
    )


def schema_contract() -> dict[str, Any]:
    """The machine-readable form of what F1P promises."""
    return {
        "schema_version": contract.SCHEMA_VERSION,
        "contract_id": contract.CONTRACT_ID,
        "task_id": TASK_ID,
        "serializer": {
            "module": "src/w2/domain/canonical_serialization.py",
            "version": contract.SERIALIZER_VERSION,
            "hash_domain": str(contract.HASH_DOMAIN),
            "note": (
                "No second serializer exists. No quant-specific HashDomain was "
                "added, because that would edit a production module; the domain "
                "string is written into every preimage instead, so introducing "
                "one later is a visible identity change."),
        },
        "market": contract.AH_MARKET,
        "allowed_factor_ids": list(contract.ALLOWED_FACTOR_IDS),
        "allowed_factor_statuses": list(contract.ALLOWED_FACTOR_STATUSES),
        "scoreless_statuses": sorted(contract.SCORELESS_STATUSES),
        "record_kinds": [contract.AS_OF_FACTOR_OBSERVATION,
                         contract.POST_EVENT_ENRICHMENT],
        "post_event_fields": sorted(contract.POST_EVENT_FIELDS),
        "protected_fields": list(contract.PROTECTED_FIELDS),
        "business_fields": list(contract.BUSINESS_FIELDS),
        "identity": {
            "factor_input_hash_preimage": [
                "contract", "hash_domain", "serializer_version", "evaluation_id",
                "attempt_id", "fixture_id", "market", "factor_id", "factor_version",
                "applied_weight", "factor_inputs", "evidence_time_utc",
                "source_capture_id", "source_capture_sha256", "source_version"],
            "factor_verdict_hash_preimage": [
                "contract", "hash_domain", "factor_input_hash", "factor_status",
                "participated", "signed_score"],
            "observation_id_preimage": [
                "contract", "hash_domain", "factor_input_hash",
                "factor_verdict_hash", "evaluated_at_utc",
                "supersedes_observation_id"],
            "format": "lowercase 64 hex",
            "created_at_excluded_from_identity": True,
        },
        "pit_rule": {
            "requirement": "evidence_time_utc < evaluated_at_utc",
            "comparison": "parsed to aware UTC; string comparison forbidden",
            "equal_fails": True,
            "naive_fails": True,
            "missing_fails": True,
            "unparseable_fails": True,
            "created_at_may_not_prove_pit": True,
            "result_time_may_not_substitute": True,
        },
        "append_only": {
            "update_allowed": False,
            "delete_allowed": False,
            "identical_rewrite": "IDEMPOTENT_NO_OP after full business-field compare",
            "same_id_different_business_fields": "OBSERVATION_ID_BUSINESS_CONFLICT",
            "revision": "new observation_id linked by supersedes_observation_id",
            "revision_requires_reason": True,
            "cycles_rejected": True,
            "revision_may_not_rewrite_prior_row": True,
        },
        "failure_codes": sorted({
            "EVIDENCE_TIME_MISSING", "TIMESTAMP_UNPARSEABLE",
            "TIMESTAMP_NOT_TIMEZONE_AWARE", "TIMESTAMP_NOT_A_STRING",
            "PIT_EVIDENCE_TIME_EQUALS_EVALUATED_AT",
            "PIT_EVIDENCE_TIME_AFTER_EVALUATED_AT", "HASH_MISSING",
            "HASH_LENGTH_INVALID", "HASH_NOT_LOWERCASE_HEX", "IDENTITY_MISMATCH",
            "APPLIED_WEIGHT_MISSING", "SIGNED_SCORE_MISSING_FOR_PARTICIPATED",
            "SCORELESS_STATUS_CARRIES_A_SCORE", "FACTOR_ID_NOT_ALLOWED",
            "FACTOR_STATUS_NOT_ALLOWED", "MARKET_OUT_OF_CONTRACT",
            "POST_EVENT_FIELD_IN_FACTOR_INPUT", "POST_EVENT_FIELD_NOT_ALLOWED",
            "POST_EVENT_FIELD_IN_AS_OF_VIEW", "OBSERVATION_ID_BUSINESS_CONFLICT",
            "SUPERSEDES_TARGET_NOT_FOUND", "SUPERSEDES_CYCLE",
            "REVISION_REASON_MISSING", "READBACK_FIELD_MISMATCH",
            "READBACK_IDENTITY_MISMATCH", "OBSERVATION_NOT_FOUND",
            "REQUIRED_FIELD_MISSING", "SCHEMA_VERSION_UNSUPPORTED",
            "RECORD_KIND_NOT_AS_OF", "FACTOR_INPUTS_NOT_A_MAPPING",
            "NUMBER_INVALID", "NUMBER_IS_BOOLEAN",
            "PARTICIPATED_FLAG_CONTRADICTS_STATUS",
        }),
        "explicitly_not": [
            "not a backfill of the frozen 148",
            "produces no model weight",
            "produces no recommendation direction",
            "does not change the live recommendation chain",
            "does not unlock F2, F3, Provider or Shadow",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)

    ledger_path = output / LEDGER_NAME
    post_event_path = output / POST_EVENT_NAME
    for path in (ledger_path, post_event_path):
        if path.exists():
            path.unlink()
    ledger = contract.ForwardFactorLedger(ledger_path)
    enrichment = contract.PostEventEnrichmentLedger(post_event_path)

    appended: list[str] = []
    for row in REFERENCE_ROWS:
        appended.append(ledger.append(build_record(row)).observation_id)
    # an identical rewrite must not add a row
    repeat = ledger.append(build_record(REFERENCE_ROWS[0]))
    # a revision appends and leaves the original untouched
    revision = ledger.append(contract.ForwardFactorObservation(
        **{**{k: v for k, v in vars(build_record(REFERENCE_ROWS[0])).items()
              if k in contract.ForwardFactorObservation.__dataclass_fields__
              and not k.startswith("_")},
           "applied_weight": "0.12",
           "observation_id": None, "factor_input_hash": None,
           "factor_verdict_hash": None,
           "supersedes_observation_id": appended[0],
           "revision_reason": "WEIGHT_CORRECTED_BY_SOURCE"}))
    # results live in a separate ledger and never touch the observations
    before_enrichment = ledger_path.read_bytes()
    enrichment.append(evaluation_id=_FIXTURE_EVALUATION,
                      payload={"score": "1-2", "settlement": "LOSS",
                               "profit_units": "-1.0"})
    enrichment_changed_observations = ledger_path.read_bytes() != before_enrichment

    for observation_id in [*appended, revision.observation_id]:
        ledger.readback(observation_id)
        view = ledger.as_of_view(observation_id)
        if contract.POST_EVENT_FIELDS & set(view):
            raise ContractRuntimeError("AS_OF_VIEW_LEAKED_POST_EVENT_FIELD")

    (output / "F1P_SCHEMA_CONTRACT.json").write_text(
        json.dumps(schema_contract(), ensure_ascii=False, sort_keys=True,
                   indent=2) + "\n", encoding="utf-8")

    rows = ledger.rows()
    result = {
        "schema_version": "w2.f1p_forward_contract_result.v1",
        "task_id": TASK_ID,
        "parent_commit": PARENT_COMMIT,
        "contract_id": contract.CONTRACT_ID,
        "serializer_version": contract.SERIALIZER_VERSION,
        "hash_domain": str(contract.HASH_DOMAIN),
        "reference_ledger_rows": len(rows),
        "reference_observations_appended": len(appended),
        "identical_rewrite_created_row": repeat.created,
        "identical_rewrite_reason": repeat.reason,
        "revision_created_new_identity": (
            revision.observation_id != appended[0]),
        "post_event_enrichment_changed_observations": (
            enrichment_changed_observations),
        "readback_verified_rows": len(rows),
        "allowed_factor_ids": list(contract.ALLOWED_FACTOR_IDS),
        "produces_model_weights": False,
        "produces_recommendation_direction": False,
        "changes_live_recommendation_chain": False,
        "is_historical_backfill_of_the_148": False,
        "unlocks_f2_or_f3_or_provider_or_shadow": False,
        "provider_calls": 0,
        "public_http_fetch": 0,
        "production_db_reads": 0,
        "production_db_writes": 0,
        "deployment_executed": False,
        "obsidian_writes": 0,
        "f2_allowed": False,
        "f3_allowed": False,
        "final_state": "FORWARD_CONTRACT_READY",
    }
    (output / "F1P_RESULT.json").write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "final_state": result["final_state"],
        "reference_ledger_rows": result["reference_ledger_rows"],
        "identical_rewrite_created_row": result["identical_rewrite_created_row"],
        "revision_created_new_identity": result["revision_created_new_identity"],
        "post_event_enrichment_changed_observations": (
            result["post_event_enrichment_changed_observations"]),
        "f2_allowed": result["f2_allowed"],
        "ledger_sha256": hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
    }, ensure_ascii=False, indent=1))
    return 0


class ContractRuntimeError(RuntimeError):
    """Raised when the reference run itself violates the contract."""


if __name__ == "__main__":
    raise SystemExit(main())
