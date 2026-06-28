from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a W2 S2 readiness report.")
    parser.add_argument("report", type=Path)
    args = parser.parse_args()

    payload = json.loads(args.report.read_text(encoding="utf-8"))
    errors: list[str] = []
    if payload.get("schema_version") == "w2.handicap_walkforward_report.v1":
        errors.extend(_validate_walkforward_report(payload))
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        print("s2 readiness report PASS")
        return 0
    if "data_source" not in payload:
        errors.append("missing data_source")
    if "authoritative" not in payload:
        errors.append("missing authoritative")
    if payload.get("beats_market") is not False:
        errors.append("beats_market must remain false")
    if payload.get("formal_enabled") is not False:
        errors.append("formal_enabled must remain false")
    if payload.get("candidate_enabled") is not False:
        errors.append("candidate_enabled must remain false")
    data_source = str(payload.get("data_source") or "")
    if ("fixtures/stage5_demo" in data_source or "stage5_demo" in data_source) and (
        payload.get("authoritative") is not False
    ):
        errors.append("stage5 demo reports must be non-authoritative")
    if payload.get("authoritative") is False:
        gate = payload.get("gate") if isinstance(payload.get("gate"), dict) else {}
        if gate.get("beats_market") is not False:
            errors.append("non-authoritative report cannot drive beats_market")
        if payload.get("dashboard_publishable") is not False:
            errors.append("non-authoritative report cannot enter dashboard")
        if payload.get("card_publishable") is not False:
            errors.append("non-authoritative report cannot enter cards")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("s2 readiness report PASS")
    return 0


def _validate_walkforward_report(payload: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if payload.get("data_source") is None:
        errors.append("missing data_source")
    if payload.get("authoritative") is None:
        errors.append("missing authoritative")
    data_source = str(payload.get("data_source") or "")
    if "stage5_demo" in data_source and payload.get("authoritative") is not False:
        errors.append("stage5 demo reports must be non-authoritative")
    raw_gate = payload.get("s2_gate")
    gate: dict[str, Any] = raw_gate if isinstance(raw_gate, dict) else {}
    raw_calibration = payload.get("calibration")
    calibration: dict[str, Any] = (
        raw_calibration if isinstance(raw_calibration, dict) else {}
    )
    if gate.get("beats_market") is not False:
        errors.append("beats_market must remain false")
    if gate.get("formal_enabled") is not False:
        errors.append("formal_enabled must remain false")
    if gate.get("candidate_enabled") is not False:
        errors.append("candidate_enabled must remain false")
    if payload.get("authoritative") is False and gate.get("beats_market") is not False:
        errors.append("non-authoritative report cannot drive beats_market")
    raw_sample = payload.get("sample")
    sample: dict[str, Any] = raw_sample if isinstance(raw_sample, dict) else {}
    included = int(sample.get("included") or 0)
    if included < 200 and calibration.get("calibration_version") != "UNVALIDATED":
        errors.append("insufficient sample must keep calibration_version=UNVALIDATED")
    return errors


if __name__ == "__main__":
    raise SystemExit(main())
