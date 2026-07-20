#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from w2.historical.football_data_co_uk import write_football_data_audits


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit local Football-Data.co.uk files.")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--report-root", type=Path)
    args = parser.parse_args()
    report_root = args.report_root or args.source_root / "reports"
    report_root.mkdir(parents=True, exist_ok=True)
    report_root.chmod(0o700)
    payloads = write_football_data_audits(args.source_root, report_root)
    inventory = payloads["FOOTBALL_DATA_LOCAL_INVENTORY"]
    f5 = payloads["FOOTBALL_DATA_F5_AUDIT"]
    market = payloads["FOOTBALL_DATA_MARKET_EVIDENCE_AUDIT"]
    print(f"inventory_status={inventory['status']}")
    print(f"file_count={inventory['file_count']}")
    print(f"f5_closing={f5['closing_canonical_facts']}")
    print(f"f5_pre_closing={f5['pre_closing_canonical_facts']}")
    print(f"phase_baseline={market['phase_baseline_candidate_matches']}")
    print(f"report_root={report_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
