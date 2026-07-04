from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, date, datetime
from typing import Any

from w2.matchday.orchestrator import build_matchday_controlled_run_plan, build_matchday_dry_run
from w2.providers.control import (
    provider_endpoint_allowlist,
    provider_refresh_min_interval_seconds,
    provider_refresh_tick_hard_cap,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a side-effect-free W2 matchday dry-run skeleton.",
    )
    parser.add_argument("--date", default="today")
    parser.add_argument("--env", default="staging", dest="environment")
    parser.add_argument("--mode", choices=("dry-run", "controlled-run"), default="dry-run")
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--approve-provider-calls", action="store_true", default=False)
    parser.add_argument("--approve-db-writes", action="store_true", default=False)
    parser.add_argument("--approve-lock-write", action="store_true", default=False)
    parser.add_argument("--approve-settlement-write", action="store_true", default=False)
    parser.add_argument("--json", action="store_true", default=False, dest="json_output")
    parser.add_argument("--as-of")
    parser.add_argument("--fixture-id", action="append", default=[])
    parser.add_argument("--kickoff-utc", action="append", default=[])
    parser.add_argument("--home-team", action="append", default=[])
    parser.add_argument("--away-team", action="append", default=[])
    parser.add_argument("--market", action="append", default=[])
    parser.add_argument("--line", action="append", default=[])
    parser.add_argument("--odds", action="append", default=[])
    args = parser.parse_args()

    mode = "dry-run" if args.dry_run else str(args.mode)
    fixture_count = _fixture_count(args.fixture_id, args.kickoff_utc)
    fixtures = _fixture_rows(
        fixture_ids=args.fixture_id,
        kickoffs=args.kickoff_utc,
        home_teams=args.home_team,
        away_teams=args.away_team,
        markets=args.market,
        lines=args.line,
        odds=args.odds,
        fixture_count=fixture_count,
    )
    as_of = _parse_utc(args.as_of) if args.as_of else datetime.now(UTC)
    football_day = _football_day(args.date, as_of)
    environment = str(args.environment)
    provider_allowed_endpoints = tuple(provider_endpoint_allowlist())
    refresh_hard_cap = provider_refresh_tick_hard_cap()
    refresh_min_interval_seconds = provider_refresh_min_interval_seconds()
    refresh_dedupe_ttl_seconds = _env_int("W2_PROVIDER_TASK_KEY_DEDUP_TTL_SECONDS", 1800)
    if mode == "controlled-run":
        payload = build_matchday_controlled_run_plan(
            football_day=football_day,
            environment=environment,
            as_of=as_of,
            fixtures=fixtures,
            approve_provider_calls=bool(args.approve_provider_calls),
            approve_db_writes=bool(args.approve_db_writes),
            approve_lock_write=bool(args.approve_lock_write),
            approve_settlement_write=bool(args.approve_settlement_write),
            provider_allowed_endpoints=provider_allowed_endpoints,
            refresh_hard_cap=refresh_hard_cap,
            refresh_min_interval_seconds=refresh_min_interval_seconds,
            refresh_dedupe_ttl_seconds=refresh_dedupe_ttl_seconds,
        )
    else:
        payload = build_matchday_dry_run(
            football_day=football_day,
            environment=environment,
            as_of=as_of,
            fixtures=fixtures,
            provider_allowed_endpoints=provider_allowed_endpoints,
            refresh_hard_cap=refresh_hard_cap,
            refresh_min_interval_seconds=refresh_min_interval_seconds,
            refresh_dedupe_ttl_seconds=refresh_dedupe_ttl_seconds,
        )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _fixture_count(fixture_ids: list[str], kickoffs: list[str]) -> int:
    if len(fixture_ids) != len(kickoffs):
        raise SystemExit("--fixture-id and --kickoff-utc counts must match")
    return len(fixture_ids)


def _fixture_rows(
    *,
    fixture_ids: list[str],
    kickoffs: list[str],
    home_teams: list[str],
    away_teams: list[str],
    markets: list[str],
    lines: list[str],
    odds: list[str],
    fixture_count: int,
) -> list[dict[str, Any]]:
    _validate_optional_count("--home-team", home_teams, fixture_count)
    _validate_optional_count("--away-team", away_teams, fixture_count)
    _validate_optional_count("--market", markets, fixture_count)
    _validate_optional_count("--line", lines, fixture_count)
    _validate_optional_count("--odds", odds, fixture_count)
    return [
        {
            "fixture_id": fixture_id,
            "kickoff_utc": kickoff,
            "home_team": _optional_at(home_teams, index),
            "away_team": _optional_at(away_teams, index),
            "market": _optional_at(markets, index),
            "line": _optional_at(lines, index),
            "odds": _optional_at(odds, index),
        }
        for index, (fixture_id, kickoff) in enumerate(zip(fixture_ids, kickoffs, strict=True))
    ]


def _validate_optional_count(name: str, values: list[str], fixture_count: int) -> None:
    if values and len(values) != fixture_count:
        raise SystemExit(f"{name} count must be zero or match --fixture-id count")


def _optional_at(values: list[str], index: int) -> str | None:
    if not values:
        return None
    return values[index]


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


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
