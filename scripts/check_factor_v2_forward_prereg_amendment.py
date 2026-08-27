from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "docs/operations/FACTOR_V2_FORWARD_COLLECTION_PREREGISTRATION_20260822.json"
NEW = ROOT / "docs/operations/FACTOR_V2_FORWARD_COLLECTION_PREREGISTRATION_RECOVERY_20260828.json"
PROTOCOL = ROOT / "docs/review_packages/V2_FORWARD_PREREG_AMENDMENT_01/PROTOCOL_FROZEN_20260828.md"
OLD_FILE_SHA256 = "cad4b549bc8a00d56ad29f1913bc8ebd582a21ee8524b86a4fb7e24480f936c1"
NEW_FILE_SHA256 = "5c6b13b50818587d381e361bafbce25f33bd7e7f52c3b090ccf02bd0def4c880"
NEW_SEMANTIC_SHA256 = "bf2b539d77a532b7c8bf9e81d2644f6f3f760ddf549719613ee2643c8aac4e98"
PROTOCOL_FILE_SHA256 = "aa0d7e1482ba7a0a31c4509a7e3a28a91a3e2acdc8ced591a6b7f7114b84dd52"


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def validate(payload: dict[str, Any]) -> None:
    _require(
        payload.get("schema_version") == "w2.factor_model.forward_collection_preregistration.v2",
        "SCHEMA_INVALID",
    )
    _require(
        payload.get("preregistration_sha256") == NEW_SEMANTIC_SHA256,
        "IDENTITY_INVALID",
    )
    supersedes = payload["supersedes"]
    _require(supersedes["file_sha256"] == OLD_FILE_SHA256, "OLD_BINDING_INVALID")
    _require(supersedes["preserve_byte_for_byte"] is True, "OLD_PRESERVATION_INVALID")
    zero = payload["zero_row_evidence"]
    _require(
        zero["classification"] == "CONFIRMED_RECORD_NOT_LIVE_QUERIED", "ZERO_ROW_LABEL_INVALID"
    )
    _require(zero["forward_sample_count"] == 0, "ZERO_ROW_COUNT_INVALID")
    _require(zero["production_reads"] == zero["production_writes"] == 0, "PRODUCTION_IO_INVALID")
    candidate = payload["candidate_identity"]
    _require(candidate["gate_1"].startswith("FAIL"), "GATE_1_INVALID")
    _require(candidate["gate_2"] == "CLOSED", "GATE_2_INVALID")
    _require(
        candidate["calibration_authority_status"] == "UNVALIDATED_NOT_ADMISSIBLE",
        "AUTHORITY_INVALID",
    )
    variants = payload["checkpoint_variants"]
    _require(
        variants["BASE_PRE_LINEUP"]["primary_confirmatory_variant"] is True, "BASE_VARIANT_INVALID"
    )
    _require(
        variants["LINEUP_CONFIRMED"]["row_admission"]
        == "NO_ROWS_ALLOWED_UNTIL_SEPARATE_PREREGISTRATION",
        "LINEUP_VARIANT_INVALID",
    )
    cohort = payload["forward_cohort"]
    _require(
        cohort["production_capture_captured_at_not_before"] is None, "UNRESOLVED_START_INVALID"
    )
    _require(cohort["cohort_start_status"] == "UNRESOLVED_NO_ROWS_ALLOWED", "COHORT_STATUS_INVALID")
    _require(
        cohort["activation_authority_required_before_first_write"] is True,
        "ACTIVATION_GUARD_INVALID",
    )
    _require(cohort["backfill_before_resolved_start_forbidden"] is True, "BACKFILL_GUARD_INVALID")
    pairing = payload["pairing_and_denominator"]
    _require(
        pairing["denominator"] == "ALL_ELIGIBLE_SCHEDULED_OPPORTUNITIES", "DENOMINATOR_INVALID"
    )
    _require(
        pairing["strict_paired_numerator"] == "fixtures_with_paired_v1_production_capture",
        "PAIRING_INVALID",
    )
    _require(pairing["point_ev_authority_epoch"] == "POINT_EV_FAIL_CLOSED", "EPOCH_INVALID")
    evaluation = payload["first_evaluation"]
    _require(
        evaluation["minimum_distinct_completed_paired_fixtures"] == 5500, "SAMPLE_RULE_INVALID"
    )
    _require(evaluation["evaluate_exactly_once"] is True, "ONE_LOOK_INVALID")
    _require(evaluation["interim_metric_evaluations_allowed"] is False, "INTERIM_LOOK_INVALID")
    _require(payload["relaxation_forbidden_after_first_sample"] is True, "RELAXATION_GUARD_INVALID")


def check() -> dict[str, Any]:
    _require(_file_sha256(OLD) == OLD_FILE_SHA256, "OLD_FILE_CHANGED")
    _require(_file_sha256(NEW) == NEW_FILE_SHA256, "NEW_FILE_CHANGED")
    _require(_file_sha256(PROTOCOL) == PROTOCOL_FILE_SHA256, "PROTOCOL_CHANGED")
    payload = json.loads(NEW.read_text(encoding="utf-8"))
    validate(payload)
    return {
        "status": "PASS",
        "old_file_sha256": OLD_FILE_SHA256,
        "successor_file_sha256": NEW_FILE_SHA256,
        "successor_identity_sha256": payload["preregistration_sha256"],
        "cohort_start": "UNRESOLVED_NO_ROWS_ALLOWED",
        "gate_1": payload["candidate_identity"]["gate_1"],
        "gate_2": payload["candidate_identity"]["gate_2"],
    }


def self_test() -> dict[str, Any]:
    payload = json.loads(NEW.read_text(encoding="utf-8"))
    caught = 0
    for path, value in (
        (("zero_row_evidence", "forward_sample_count"), 1),
        (("checkpoint_variants", "LINEUP_CONFIRMED", "row_admission"), "ELIGIBLE"),
        (("forward_cohort", "production_capture_captured_at_not_before"), "2026-08-22T00:00:00Z"),
        (("pairing_and_denominator", "strict_paired_numerator"), "LOOSE_FIXTURE_JOIN"),
        (("first_evaluation", "interim_metric_evaluations_allowed"), True),
    ):
        mutant = copy.deepcopy(payload)
        target: dict[str, Any] = mutant
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        try:
            validate(mutant)
        except ValueError:
            caught += 1
    _require(caught == 5, "SELF_TEST_MUTANT_ESCAPED")
    return {"status": "PASS", "mutants_caught": caught}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test-check", action="store_true")
    args = parser.parse_args()
    result = self_test() if args.self_test_check else check()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
