from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from w2.api.repository import ReadModelService
from w2.infrastructure.database import create_engine
from w2.tracking.formal_results import (
    build_tracking_report,
    capture_formal_locks,
    capture_formal_snapshots,
    settle_formal_snapshots,
)


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
    parser = argparse.ArgumentParser(
        description="Capture and settle W2 formal recommendation tracking artifacts."
    )
    parser.add_argument("--mode", choices=["capture", "settle", "report", "all"], default="all")
    parser.add_argument("--window", default="all", choices=["today", "next36", "results", "all"])
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--no-dry-run", action="store_false", dest="dry_run")
    parser.add_argument("--write-artifacts", action="store_true")
    parser.add_argument("--write-db-locks", action="store_true")
    parser.add_argument("--runtime-root", type=Path, default=None)
    parser.add_argument("--output-report", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    service = ReadModelService()
    release_sha = os.getenv("W2_GIT_SHA") or os.getenv("W2_RELEASE_ID")
    output: dict[str, Any] = {
        "mode": args.mode,
        "dry_run": args.dry_run,
        "write_artifacts": args.write_artifacts,
        "not_a_formal_gate": True,
        "posthoc_only": True,
    }
    if args.mode in {"capture", "all"}:
        cards = dashboard_cards(service, args.window)
        output["capture"] = capture_formal_snapshots(
            cards,
            dry_run=args.dry_run,
            write_artifacts=args.write_artifacts,
            runtime_root=args.runtime_root,
            release_sha=release_sha,
        )
        if args.write_db_locks:
            engine = create_engine()
            with Session(engine) as session:
                output["lock_capture"] = capture_formal_locks(
                    cards,
                    session=session,
                    release_sha=release_sha,
                )
                if not args.dry_run:
                    session.commit()
                else:
                    session.rollback()
    if args.mode in {"settle", "all"}:
        cards = dashboard_cards(service, "all")
        output["settle"] = settle_formal_snapshots(
            cards,
            dry_run=args.dry_run,
            write_artifacts=args.write_artifacts,
            runtime_root=args.runtime_root,
        )
    if args.mode in {"report", "all"}:
        output["report"] = build_tracking_report(
            runtime_root=args.runtime_root,
            output_report=args.output_report,
            write=args.write_artifacts and not args.dry_run,
        )
    if args.json_output:
        print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(f"status=PASS mode={args.mode} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
