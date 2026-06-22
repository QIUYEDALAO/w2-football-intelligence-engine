from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from w2.api.dashboard_read_models import MatchdaySnapshotProjector, write_projection
from w2.infrastructure.database import create_engine


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Project validated matchday snapshots to dashboard read models."
    )
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--fixture-id")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--database-url-from-env", action="store_true")
    args = parser.parse_args()
    if not args.latest:
        parser.error("--latest is required for Stage10B projector")
    projector = MatchdaySnapshotProjector(args.snapshot_root)
    projection = projector.project_latest(args.fixture_id)
    if not args.dry_run:
        if not args.database_url_from_env:
            parser.error("--database-url-from-env is required when writing read models")
        engine = create_engine()
        write_projection(engine, projection)
    payload: dict[str, Any] = {
        "status": "DRY_RUN" if args.dry_run else "PROJECTED",
        "fixture_id": projection.fixture["fixture_id"],
        "captured_at": projection.fixture["captured_at"],
        "decision_status": projection.fixture["decision_status"],
        "bookmaker_count": projection.fixture["bookmaker_count"],
        "remaining_quota": projection.provider["remaining_quota"],
        "checkpoint_keys": sorted(projection.checkpoint_payloads),
        "formal_recommendation": projection.fixture["formal_recommendation"],
        "candidate": projection.fixture["candidate"],
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
