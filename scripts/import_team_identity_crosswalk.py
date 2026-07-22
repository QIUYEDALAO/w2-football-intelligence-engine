#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from w2.historical.fah_repository import FahDataFoundationRepository
from w2.lineups.value_identity import import_team_crosswalk_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Import audited team identity crosswalk rows.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--database-url")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write and not args.database_url:
        parser.error("--write requires --database-url")
    rows = import_team_crosswalk_file(args.input)
    write_summary = None
    if args.write:
        repository = FahDataFoundationRepository.from_url(str(args.database_url))
        write_summary = repository.write_team_crosswalks([row.as_dict() for row in rows])
    payload = {
        "schema_version": "w2.team_identity_crosswalk_import.v1",
        "dry_run": not args.write,
        "database_write": bool(write_summary and write_summary.db_writes),
        "write_summary": write_summary.as_dict() if write_summary else None,
        "total": len(rows),
        "approved": sum(1 for row in rows if row.review_status == "APPROVED"),
        "rows": [row.as_dict() for row in rows],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
