#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from w2.tracking.forward_ledger_performance import load_forward_ledger_records_with_status
from w2.tracking.strict_ah_canary import check_strict_ah_canary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the read-only corrected Strict AH canary checker."
    )
    parser.add_argument(
        "--runtime-root",
        type=Path,
        required=True,
        help="Runtime root containing forward_outcome_ledger/*.jsonl.",
    )
    args = parser.parse_args()
    ledger_root = args.runtime_root / "forward_outcome_ledger"
    if not ledger_root.exists() and list(args.runtime_root.glob("*.jsonl")):
        ledger_root = args.runtime_root
    records, source_read_status, corruption_count = load_forward_ledger_records_with_status(
        ledger_root
    )
    report = check_strict_ah_canary(records)
    report["source_read_status"] = source_read_status
    report["source_corruption_count"] = corruption_count
    if source_read_status != "PASS":
        report["status"] = "CANARY_SOURCE_BLOCKED"
        report["exit_code"] = 2
        report["blockers"] = [
            *report.get("blockers", []),
            f"SOURCE_READ_{source_read_status}",
        ]
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
