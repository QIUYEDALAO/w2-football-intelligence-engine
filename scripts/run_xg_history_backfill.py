from __future__ import annotations

import argparse
import json
from pathlib import Path

from w2.ingestion.xg_backfill import (
    ProStatisticsBackfillConfig,
    ProStatisticsBackfillService,
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
    parser.add_argument("--pro-batch", type=int, choices=(1, 2, 3))
    parser.add_argument("--request-budget", type=int, default=5500)
    parser.add_argument("--requests-per-minute", type=int, default=60)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute saved-raw materialization without database writes.",
    )
    args = parser.parse_args()
    if args.dry_run and not args.saved_raw_only:
        parser.error("--dry-run requires --saved-raw-only")
    if args.pro_batch:
        backfill = ProStatisticsBackfillService(
            config=ProStatisticsBackfillConfig(
                batch=args.pro_batch,
                request_budget=args.request_budget,
                requests_per_minute=args.requests_per_minute,
            )
        ).run()
        materialized = materialize_saved_xg()
        payload = {
            "backfill": backfill.as_dict(),
            "materialization": materialized.as_dict(),
        }
        report_path = args.report or Path(
            f"reports/W2_XG_PRO_STATISTICS_BACKFILL_BATCH_{args.pro_batch}.json"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return
    result = (
        materialize_saved_xg(persist=not args.dry_run)
        if args.saved_raw_only
        else run_xg_history_backfill()
    )
    report_path = args.report or Path("reports/W2_XG_HISTORY_BACKFILL.json")
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
