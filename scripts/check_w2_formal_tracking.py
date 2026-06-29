from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from w2.tracking.formal_results import (
    MIN_BUCKET_SAMPLES_FOR_RATE,
    json_paths,
    load_json,
    parse_dt,
    report_path,
    settlement_dir,
    snapshot_dir,
)


def add_error(errors: list[str], message: str) -> None:
    errors.append(message)


def validate_snapshot(path: Path, payload: dict[str, Any], errors: list[str]) -> None:
    if payload.get("immutable") is not True:
        add_error(errors, f"{path}: immutable must be true")
    if payload.get("formal_recommendation") is not True:
        add_error(errors, f"{path}: formal_recommendation must be true")
    if payload.get("candidate") is not False:
        add_error(errors, f"{path}: candidate must be false")
    if payload.get("formal_result_tracking", {}).get("not_a_formal_gate") is not True:
        add_error(errors, f"{path}: tracking must be marked not_a_formal_gate")
    as_of = parse_dt(payload.get("as_of"))
    kickoff = parse_dt(payload.get("kickoff_utc"))
    if as_of is None or kickoff is None or as_of >= kickoff:
        add_error(errors, f"{path}: snapshot as_of must be before kickoff")


def validate_settlement(path: Path, payload: dict[str, Any], errors: list[str]) -> None:
    outcome = payload.get("settlement_outcome")
    if outcome not in {"WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS", "VOID"}:
        add_error(errors, f"{path}: invalid settlement_outcome {outcome}")
    if outcome == "VOID" and payload.get("sample_included") is not False:
        add_error(errors, f"{path}: VOID must be excluded from sample")
    if outcome == "PUSH" and payload.get("win_included") is not False:
        add_error(errors, f"{path}: PUSH must not count as win")
    if payload.get("not_a_formal_gate") is not True:
        add_error(errors, f"{path}: settlement must be marked not_a_formal_gate")


def validate_report(payload: dict[str, Any], errors: list[str]) -> None:
    if payload.get("not_a_formal_gate") is not True:
        add_error(errors, "report: not_a_formal_gate must be true")
    if payload.get("posthoc_only") is not True:
        add_error(errors, "report: posthoc_only must be true")
    sample_count = payload.get("sample_count", 0)
    if isinstance(sample_count, int) and sample_count < MIN_BUCKET_SAMPLES_FOR_RATE:
        if payload.get("win_rate") is not None or payload.get("roi") is not None:
            add_error(errors, "report: low sample must hide win_rate and roi")
    for dimension, rows in payload.get("buckets", {}).items():
        if not isinstance(rows, list):
            add_error(errors, f"report: bucket {dimension} must be a list")
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get("sample_count", 0) < MIN_BUCKET_SAMPLES_FOR_RATE:
                if row.get("win_rate") is not None or row.get("roi") is not None:
                    add_error(
                        errors,
                        f"report: low-sample bucket {dimension}/{row.get('bucket')} exposes rates",
                    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate W2 formal tracking artifacts.")
    parser.add_argument("--runtime-root", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    errors: list[str] = []
    snapshot_count = 0
    settlement_count = 0
    for path in json_paths(snapshot_dir(args.runtime_root)):
        payload = load_json(path, {})
        if isinstance(payload, dict):
            snapshot_count += 1
            validate_snapshot(path, payload, errors)
    for path in json_paths(settlement_dir(args.runtime_root)):
        payload = load_json(path, {})
        if isinstance(payload, dict):
            settlement_count += 1
            validate_settlement(path, payload, errors)
    report_payload = load_json(report_path(args.report), {})
    if isinstance(report_payload, dict) and report_payload:
        validate_report(report_payload, errors)
    output = {
        "ok": not errors,
        "snapshot_count": snapshot_count,
        "settlement_count": settlement_count,
        "report_present": bool(report_payload),
        "errors": errors,
    }
    if args.json_output:
        print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(output)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
