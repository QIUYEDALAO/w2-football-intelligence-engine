#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from w2.historical.football_data_co_uk import write_football_data_ingest_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build private Football-Data.co.uk canonical evidence artifacts."
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path)
    args = parser.parse_args()
    artifact_root = args.artifact_root or args.source_root / "reports" / "ingest_01"
    artifact_root.mkdir(parents=True, exist_ok=True)
    artifact_root.chmod(0o700)
    result = write_football_data_ingest_artifacts(args.source_root, artifact_root)
    manifest = result["manifest"]
    coverage = result["f5_coverage"]
    baseline = result["market_baseline_candidate"]
    print(f"source_snapshots={manifest['source_snapshot_count']}")
    print(f"closing_ah_facts={manifest['closing_ah_fact_count']}")
    print(f"pre_closing_ah_facts={manifest['pre_closing_ah_fact_count']}")
    print(f"phase_market_evidence={manifest['phase_market_evidence_count']}")
    print(f"f5_ready={manifest['f5_ready_count']}")
    print(f"f5_coverage_status={coverage['status']}")
    print(f"market_baseline_status={baseline['status']}")
    print(f"artifact_root={artifact_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
