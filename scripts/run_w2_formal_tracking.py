from __future__ import annotations

import argparse
import json
import os
from typing import Any

from sqlalchemy.orm import Session

from w2.api.repository import ReadModelService
from w2.tracking.formal_results import (
    build_tracking_report,
    capture_formal_locks,
    capture_formal_snapshots,
    settle_formal_snapshots,
)
from w2.tracking.outcome_ledger_repository import OutcomeLedgerRepository

WRITE_CONFIRMATION_PHRASE = "EVAL_01A_FORMAL_TRACKING"  # noqa: S105


def dashboard_cards(service: ReadModelService, window: str) -> list[dict[str, Any]]:
    payload = service.dashboard(window=window, include_debug=True)
    data_profile = payload.get("data_profile") or payload.get("data_source")
    rows = []
    for row in payload.get("all", []):
        if not isinstance(row, dict):
            continue
        if data_profile and not (row.get("data_profile") or row.get("data_source")):
            row = {**row, "data_profile": data_profile}
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture and settle formal tracking in DB.")
    parser.add_argument("--mode", choices=["capture", "settle", "report", "all"], default="all")
    parser.add_argument("--window", default="all", choices=["today", "next36", "results", "all"])
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--write-db", action="store_true")
    parser.add_argument("--confirm-write")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()
    if args.write_db and args.dry_run:
        parser.error("--write-db requires --no-dry-run")
    if args.write_db and args.confirm_write != WRITE_CONFIRMATION_PHRASE:
        parser.error(f"--confirm-write {WRITE_CONFIRMATION_PHRASE} is required")

    repository = OutcomeLedgerRepository()
    service = ReadModelService()
    release_sha = os.getenv("W2_GIT_SHA") or os.getenv("W2_RELEASE_ID")
    output: dict[str, Any] = {
        "mode": args.mode,
        "dry_run": args.dry_run,
        "write_db": args.write_db,
        "not_a_formal_gate": True,
        "posthoc_only": True,
    }
    if args.mode in {"capture", "all"}:
        cards = dashboard_cards(service, args.window)
        output["capture"] = capture_formal_snapshots(
            cards,
            repository=repository,
            dry_run=args.dry_run,
            write_db=args.write_db,
            release_sha=release_sha,
        )
        with Session(repository.engine) as session:
            output["lock_capture"] = capture_formal_locks(
                cards,
                session=session,
                release_sha=release_sha,
            )
            session.commit() if args.write_db and not args.dry_run else session.rollback()
    if args.mode in {"settle", "all"}:
        output["settle"] = settle_formal_snapshots(
            repository=repository,
            dry_run=args.dry_run,
            write_db=args.write_db,
        )
    if args.mode in {"report", "all"}:
        output["report"] = build_tracking_report(repository=repository)
    if args.json_output:
        print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(f"status=PASS mode={args.mode} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
