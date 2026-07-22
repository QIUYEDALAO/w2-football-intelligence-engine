from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, date, datetime
from typing import Any

from w2.domain.environment_policy import build_environment_policy_stamp
from w2.providers.control import (
    provider_endpoint_allowlist,
    provider_refresh_tick_hard_cap,
)
from w2.refresh.matchday_schedule import (
    MatchdayRefreshPolicy,
    build_matchday_refresh_plan,
)

EFFECTIVE_ENDPOINT_ORDER = ("status", "fixtures", "odds", "lineups")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a dry-run W2 matchday refresh plan without provider or DB writes.",
    )
    parser.add_argument("--date", default="today")
    parser.add_argument("--env", default="staging", dest="environment")
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--json", action="store_true", default=False, dest="json_output")
    parser.add_argument("--fixture-id", action="append", default=[])
    parser.add_argument("--competition-id")
    parser.add_argument("--kickoff-utc", action="append", default=[])
    parser.add_argument("--as-of")
    args = parser.parse_args()

    if not args.dry_run:
        raise SystemExit("Only --dry-run is supported in this PR")
    if not args.fixture_id or not args.kickoff_utc:
        raise SystemExit(
            "Local dry-run requires --fixture-id and --kickoff-utc; staging DB read is not used",
        )
    if len(args.fixture_id) != len(args.kickoff_utc):
        raise SystemExit("--fixture-id and --kickoff-utc counts must match")
    if args.fixture_id and not args.competition_id:
        raise SystemExit("--competition-id is required when fixtures are provided")

    as_of = _parse_utc(args.as_of) if args.as_of else datetime.now(UTC)
    fixtures = [
        {
            "fixture_id": fixture_id,
            "competition_id": args.competition_id,
            "kickoff_utc": kickoff,
        }
        for fixture_id, kickoff in zip(args.fixture_id, args.kickoff_utc, strict=True)
    ]
    policy = MatchdayRefreshPolicy(
        competition_id=args.competition_id,
        allowed_endpoints=tuple(provider_endpoint_allowlist()),
        tick_hard_cap=provider_refresh_tick_hard_cap(),
        min_interval_seconds=_env_int("W2_PROVIDER_REFRESH_MIN_INTERVAL_SECONDS", 900),
        dedupe_ttl_seconds=_env_int("W2_PROVIDER_TASK_KEY_DEDUP_TTL_SECONDS", 1800),
    )
    ticks = build_matchday_refresh_plan(fixtures, as_of=as_of, policy=policy)
    blocked_ticks = [tick for tick in ticks if tick.status == "BLOCKED"]
    effective_endpoints = {
        endpoint for tick in ticks for endpoint in tick.allowed_endpoints
    }
    payload: dict[str, Any] = {
        "football_day": _football_day(args.date, as_of).isoformat(),
        "environment": args.environment,
        "environment_policy": build_environment_policy_stamp(args.environment),
        "as_of": _iso(as_of),
        "fixture_count": len(fixtures),
        "ticks": [tick.as_dict() for tick in ticks],
        "projected_calls_by_tick": {tick.task_key: tick.projected_calls for tick in ticks},
        "configured_endpoint_allowlist": list(policy.allowed_endpoints),
        "endpoint_allowlist": [
            endpoint for endpoint in EFFECTIVE_ENDPOINT_ORDER if endpoint in effective_endpoints
        ],
        "hard_cap": policy.tick_hard_cap,
        "effective_min_interval_seconds": policy.effective_min_interval_seconds,
        "dedupe_ttl_seconds": policy.dedupe_ttl_seconds,
        "skipped_endpoints": sorted(
            {endpoint for tick in ticks for endpoint in tick.skipped_endpoints},
        ),
        "blocked_ticks": [tick.task_key for tick in blocked_ticks],
        "would_enqueue": False,
        "provider_calls": 0,
        "db_writes": 0,
        "ledger_contract": {
            "provider_request_logs": "required_on_real_execution",
            "quota_usage": "required_on_real_execution",
            "future_refresh_run_audit": "required_on_real_execution",
            "raw_payload": "required_on_real_execution",
            "planned_calls_equal_provider_request_logs_delta": True,
            "dry_run_writes": False,
        },
    }
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _football_day(raw: str, as_of: datetime) -> date:
    if raw == "today":
        return as_of.astimezone(UTC).date()
    return date.fromisoformat(raw)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


if __name__ == "__main__":
    sys.exit(main())
