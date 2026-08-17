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
    parser.add_argument(
        "--window",
        default="next7",
        choices=["today", "next36", "next7", "future", "all"],
    )
    parser.add_argument("--import-runtime-ledger", action="store_true")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--legacy-recovery-manifest", type=Path)
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--write-db", action="store_true")
    parser.add_argument("--confirm-write")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.write_db and args.dry_run:
        parser.error("--write-db requires --no-dry-run")
    if args.legacy_recovery_manifest is not None and not args.import_runtime_ledger:
        parser.error("--legacy-recovery-manifest requires --import-runtime-ledger")

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
            legacy_recovery_manifest=args.legacy_recovery_manifest,
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
    elif args.import_runtime_ledger:
        print(
            "status={status} source_files={source_files} source_records={source_records} "
            "db_records={db_records} already_imported={already_imported} "
            "source_sha256={source_sha256} db_sha256={db_sha256} "
            "reconciliation={reconciliation} db_writes={db_writes}".format(
                status=payload["status"],
                source_files=payload["source_file_count"],
                source_records=payload["source_record_count"],
                db_records=payload["db_record_count"],
                already_imported=payload["already_imported_count"],
                source_sha256=payload["source_canonical_sha256"],
                db_sha256=payload["db_canonical_sha256"],
                reconciliation=payload["reconciliation_status"],
                db_writes=payload["db_writes"],
            )
        )
    else:
        print(
            "status={status} dry_run={dry_run} records={records} written={written}".format(
                status=payload["status"],
                dry_run=payload["dry_run"],
                records=payload["record_count"],
                written=payload["written"],
            )
        )
    return (
        0
        if payload.get("status") == "PASS"
        and payload.get("reconciliation_status") not in {"FAIL", "BLOCKED"}
        and not payload.get("malformed_count")
        and not payload.get("result_conflict_count")
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
