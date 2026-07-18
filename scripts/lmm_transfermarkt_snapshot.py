#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.lineups.transfermarkt import load_player_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download and inspect the versioned Transfermarkt player snapshot."
    )
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    observed_at = datetime.fromisoformat(args.observed_at.replace("Z", "+00:00")).astimezone(UTC)
    snapshot = load_player_snapshot(observed_at=observed_at)
    imported = 0
    mapped = 0
    if args.write:
        repository = FutureRefreshDbRepository()
        imported = repository.import_transfermarkt_player_snapshot(
            source_url=snapshot.source_url,
            source_sha256=snapshot.source_sha256,
            observed_at=snapshot.observed_at,
            rows=list(snapshot.rows),
        )
        for fixture_id in repository.structured_lineup_fixture_ids():
            mapped += repository.materialize_player_identity_mappings(
                fixture_id=fixture_id,
                as_of=datetime.now(UTC),
            )
    valued = sum(row.get("market_value_eur") is not None for row in snapshot.rows)
    positioned = sum(bool(row.get("position")) for row in snapshot.rows)
    print(
        json.dumps(
            {
                "schema_version": "w2.transfermarkt_snapshot_manifest.v1",
                "source_url": snapshot.source_url,
                "source_sha256": snapshot.source_sha256,
                "observed_at": snapshot.observed_at.isoformat(),
                "player_count": len(snapshot.rows),
                "valued_player_count": valued,
                "positioned_player_count": positioned,
                "db_writes": imported,
                "write_enabled": bool(args.write),
                "identity_mapping_rows": mapped,
                "provider_calls": 0,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
