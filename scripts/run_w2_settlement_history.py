#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from w2.infrastructure.database import create_engine
from w2.settlement.history import (
    WRITE_CONFIRMATION_PHRASE,
    SettlementHistoryError,
    run_settlement_history,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run W2 settlement history automation.")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--write-db", action="store_true")
    parser.add_argument("--confirm-write")
    parser.add_argument("--json", action="store_true", default=True)
    args = parser.parse_args(argv)

    dry_run = not args.write_db
    try:
        engine = create_engine()
        with Session(engine) as session:
            result = run_settlement_history(
                session=session,
                dry_run=dry_run,
                write_db=args.write_db,
                confirm_write=args.confirm_write,
                now=datetime.now(UTC),
            )
        _emit(result)
        return 0
    except (SettlementHistoryError, Exception) as exc:
        payload: dict[str, Any] = {
            "status": "FAILED",
            "error": str(exc),
            "db_writes": 0,
            "provider_calls": 0,
            "write_confirmation_phrase": WRITE_CONFIRMATION_PHRASE,
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
