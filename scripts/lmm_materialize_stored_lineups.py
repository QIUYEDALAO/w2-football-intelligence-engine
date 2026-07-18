#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize already-saved lineup payloads without provider access."
    )
    parser.add_argument("--limit", type=int, default=512)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    repository = FutureRefreshDbRepository()
    candidates = repository.stored_lineup_materialization_candidates(limit=args.limit)
    result = {
        "schema_version": "w2.stored_lineup_materialization.v1",
        "candidate_payload_count": len(candidates),
        "materialized_snapshot_count": 0,
        "skipped_incomplete_count": 0,
        "provider_calls": 0,
        "write_enabled": bool(args.write),
    }
    if args.write:
        result.update(repository.materialize_stored_lineup_payloads(limit=args.limit))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
