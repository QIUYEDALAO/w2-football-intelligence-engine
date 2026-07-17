from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from w2.api.repository import ReadModelService  # noqa: E402
from w2.config import get_settings  # noqa: E402
from w2.dashboard.day_view import build_dashboard_day_view  # noqa: E402
from w2.tracking.forward_outcome_ledger import run_forward_outcome_ledger  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture read-only W2 forward outcome ledger rows from DayView."
    )
    parser.add_argument("--date")
    parser.add_argument("--window", default="next36", choices=["today", "next36", "future", "all"])
    parser.add_argument("--day-view-json", type=Path)
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--write-artifacts", action="store_true")
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.day_view_json is not None:
        day_view = json.loads(args.day_view_json.read_text(encoding="utf-8"))
    else:
        service = ReadModelService()
        dashboard = service.dashboard(
            target_date=args.date,
            window=args.window,
            include_debug=False,
        )
        day_view = build_dashboard_day_view(
            dashboard,
            environment=get_settings().environment.value,
        )
    payload = run_forward_outcome_ledger(
        day_view,
        dry_run=args.dry_run,
        write_artifacts=args.write_artifacts,
        runtime_root=args.runtime_root,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(
            "status={status} dry_run={dry_run} records={records} written={written}".format(
                status=payload["status"],
                dry_run=payload["dry_run"],
                records=payload["record_count"],
                written=payload["written"],
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
