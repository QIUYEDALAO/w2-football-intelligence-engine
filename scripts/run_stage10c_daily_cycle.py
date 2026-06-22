from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

from w2.matchday.cards import DailyMatchdayCycle

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Stage10C daily matchday dry cycle")
    parser.add_argument("--date", default=None)
    parser.add_argument("--competition-id", default=None)
    parser.add_argument("--timezone", default="UTC")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--request-budget", type=int, default=100)
    parser.add_argument(
        "--snapshot-root",
        default=str(ROOT / "runtime/matchday/argentina-austria-20260622/snapshots"),
    )
    args = parser.parse_args()
    target = date.fromisoformat(args.date) if args.date else datetime.now(UTC).date()
    cycle = DailyMatchdayCycle(
        snapshot_root=Path(args.snapshot_root),
        schedule_path=ROOT / "config/policies/matchday_schedule.v1.json",
        reports_dir=ROOT / "reports",
    )
    result = cycle.run(target_date=target, dry_run=args.dry_run)
    result["request_budget"] = args.request_budget
    result["competition_id_filter"] = args.competition_id
    result["timezone"] = args.timezone
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
