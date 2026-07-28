from __future__ import annotations

import argparse
import json
from typing import Any

from w2.tracking.formal_results import (
    MIN_BUCKET_SAMPLES_FOR_RATE,
    build_tracking_report,
    load_settlements,
    load_snapshots,
    parse_dt,
)
from w2.tracking.outcome_ledger_repository import OutcomeLedgerRepository


def validate_snapshot(payload: dict[str, Any], errors: list[str]) -> None:
    if payload.get("immutable") is not True:
        errors.append("snapshot: immutable must be true")
    if payload.get("formal_recommendation") is not True:
        errors.append("snapshot: formal_recommendation must be true")
    if payload.get("candidate") is not False:
        errors.append("snapshot: candidate must be false")
    if payload.get("formal_result_tracking", {}).get("not_a_formal_gate") is not True:
        errors.append("snapshot: tracking must be marked not_a_formal_gate")
    as_of = parse_dt(payload.get("as_of"))
    kickoff = parse_dt(payload.get("kickoff_utc"))
    if as_of is None or kickoff is None or as_of >= kickoff:
        errors.append("snapshot: as_of must be before kickoff")


def validate_settlement(payload: dict[str, Any], errors: list[str]) -> None:
    outcome = payload.get("settlement_outcome")
    if outcome not in {"WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS", "VOID"}:
        errors.append(f"settlement: invalid outcome {outcome}")
    if outcome == "VOID" and payload.get("sample_included") is not False:
        errors.append("settlement: VOID must be excluded from sample")
    if outcome == "PUSH" and payload.get("win_included") is not False:
        errors.append("settlement: PUSH must not count as win")
    if payload.get("not_a_formal_gate") is not True:
        errors.append("settlement: not_a_formal_gate must be true")


def validate_report(payload: dict[str, Any], errors: list[str]) -> None:
    if payload.get("not_a_formal_gate") is not True or payload.get("posthoc_only") is not True:
        errors.append("report: safety markers missing")
    if payload.get("sample_count", 0) < MIN_BUCKET_SAMPLES_FOR_RATE:
        if payload.get("win_rate") is not None or payload.get("roi") is not None:
            errors.append("report: low sample must hide win_rate and roi")
    for dimension, rows in payload.get("buckets", {}).items():
        if not isinstance(rows, list):
            errors.append(f"report: bucket {dimension} must be a list")
            continue
        for row in rows:
            if (
                isinstance(row, dict)
                and row.get("sample_count", 0) < MIN_BUCKET_SAMPLES_FOR_RATE
                and (row.get("win_rate") is not None or row.get("roi") is not None)
            ):
                errors.append(
                    f"report: low-sample bucket {dimension}/{row.get('bucket')} exposes rates"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate W2 formal tracking DB rows.")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()
    repository = OutcomeLedgerRepository()
    errors: list[str] = []
    snapshots = load_snapshots(repository)
    settlements = load_settlements(repository)
    report = build_tracking_report(repository=repository)
    for payload in snapshots:
        validate_snapshot(payload, errors)
    for payload in settlements:
        validate_settlement(payload, errors)
    validate_report(report, errors)
    output = {
        "ok": not errors,
        "snapshot_count": len(snapshots),
        "settlement_count": len(settlements),
        "errors": errors,
    }
    print(
        json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2)
        if args.json_output
        else output
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
