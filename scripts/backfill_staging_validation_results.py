from __future__ import annotations

import argparse
import json

from w2.api.repository import future_refresh_db_repository
from w2.config import get_settings
from w2.operations.result_backfill import (
    APPROVED_FIXTURE_IDS,
    discover_missing_validation_results,
    run_restricted_result_backfill,
)
from w2.providers.api_football import ApiFootballClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Restricted staging validation result backfill")
    parser.add_argument("--fixture-id", action="append", default=[])
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    discovered = discover_missing_validation_results(settings.resolved_runtime_root)
    requested = args.fixture_id or [row["fixture_id"] for row in discovered]
    summary: dict[str, object] = {
        "discovered": discovered,
        "approved": sorted(APPROVED_FIXTURE_IDS),
    }
    if not args.live:
        summary.update({"status": "DISCOVERY_ONLY", "provider_calls": 0})
    else:
        summary["result"] = run_restricted_result_backfill(
            requested,
            environment=settings.environment,
            client=ApiFootballClient(
                allow_live=True,
                allowed_live_endpoints=frozenset({"fixtures"}),
            ),
            repository=future_refresh_db_repository() if args.apply else None,
            apply=args.apply,
        )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
