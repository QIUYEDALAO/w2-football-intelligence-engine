from __future__ import annotations

import argparse
from pathlib import Path

from w2.ingestion.xg_backfill import (
    materialize_saved_xg,
    run_xg_history_backfill,
    write_backfill_report,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--saved-raw-only",
        action="store_true",
        help="Materialize persisted fixture/statistics evidence with zero Provider calls.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute saved-raw materialization without database writes.",
    )
    args = parser.parse_args()
    if args.dry_run and not args.saved_raw_only:
        parser.error("--dry-run requires --saved-raw-only")
    result = (
        materialize_saved_xg(persist=not args.dry_run)
        if args.saved_raw_only
        else run_xg_history_backfill()
    )
    report_path = Path("reports/W2_XG_HISTORY_BACKFILL.json")
    write_backfill_report(report_path, result)
    print(f"xg_history_backfill report={report_path}")
    print(f"team_count={result.team_count}")
    print(f"historical_fixture_count={result.historical_fixture_count}")
    print(f"statistics_request_count={result.statistics_request_count}")
    print(f"team_xg_match_rows={result.team_xg_match_rows}")
    print(f"rolling_snapshot_rows={result.rolling_snapshot_rows}")
    print(f"remaining_quota={result.remaining_quota}")
    print(f"blockers={result.blockers}")


if __name__ == "__main__":
    main()
