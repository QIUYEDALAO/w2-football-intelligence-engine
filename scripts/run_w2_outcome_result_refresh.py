from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from w2.tracking.outcome_result_refresh import run_outcome_result_refresh  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize terminal results from already captured DB fixture payloads."
    )
    parser.add_argument("--fixture-id", action="append")
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--write-db", action="store_true")
    args = parser.parse_args()
    if args.write_db and args.dry_run:
        parser.error("--write-db requires --no-dry-run")
    payload = run_outcome_result_refresh(
        fixture_ids=args.fixture_id,
        dry_run=args.dry_run,
        write_db=args.write_db,
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
