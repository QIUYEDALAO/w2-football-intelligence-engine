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
from w2.tracking.outcome_ledger_repository import (  # noqa: E402
    OutcomeLedgerRepository,
    import_runtime_ledger,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture read-only W2 forward outcome ledger rows from DayView."
    )
    parser.add_argument("--date")
    parser.add_argument("--window", default="next36", choices=["today", "next36", "future", "all"])
    parser.add_argument("--import-runtime-ledger", action="store_true")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--write-db", action="store_true")
    parser.add_argument("--confirm-write")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.write_db and args.dry_run:
        parser.error("--write-db requires --no-dry-run")

    repository = OutcomeLedgerRepository()
    if args.import_runtime_ledger:
        if args.source_root is None:
            parser.error("--source-root is required with --import-runtime-ledger")
        payload = import_runtime_ledger(
            repository,
            args.source_root,
            dry_run=args.dry_run,
            write_db=args.write_db,
            confirm_write=args.confirm_write,
        )
    else:
        service = ReadModelService()
        dashboard = service.dashboard(
            target_date=args.date,
            window=args.window,
            include_debug=False,
        )
        payload = run_forward_outcome_ledger(
            build_dashboard_day_view(
                dashboard,
                environment=get_settings().environment.value,
            ),
            repository=repository,
            dry_run=args.dry_run,
            write_db=args.write_db,
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
