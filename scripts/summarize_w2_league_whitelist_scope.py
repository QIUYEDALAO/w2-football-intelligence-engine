from __future__ import annotations

import argparse
import json
from typing import Any

from w2.competitions.league_whitelist_scope import (
    LeagueWhitelistScope,
    load_league_whitelist_scope,
)
from w2.competitions.registry import CompetitionRegistry, CompetitionRegistryEntry

SOURCE = "scripts.summarize_w2_league_whitelist_scope.v1"
DAILY_AUDIT_HARD_CAP = 90


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize the full W2 league whitelist audit scope without provider calls.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    payload = build_scope_summary()
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=None if args.json_output else 2,
        )
    )
    return 0


def build_scope_summary(
    *,
    provider_calls_used_today: int = 0,
    daily_audit_hard_cap: int = DAILY_AUDIT_HARD_CAP,
    registry: CompetitionRegistry | None = None,
) -> dict[str, Any]:
    scope = load_league_whitelist_scope(registry)
    inventory = [
        _inventory_item(scope.entries[competition_id], scope)
        for competition_id in scope.all_whitelist
    ]
    remaining_cap = remaining_provider_cap(
        provider_calls_used_today,
        daily_audit_hard_cap=daily_audit_hard_cap,
    )
    return {
        "status": "PASS",
        "source": SOURCE,
        "competition_count": len(inventory),
        "remaining_unaudited_count": len(scope.remaining_unaudited),
        "remaining_unaudited_whitelist": list(scope.remaining_unaudited),
        "inventory": inventory,
        "provider_calls": 0,
        "db_reads": 1,
        "import_time_db_reads": 0,
        "runtime_scope_db_reads": 1,
        "db_writes": 0,
        "provider_calls_used_today_by_league_whitelist": provider_calls_used_today,
        "daily_audit_hard_cap": daily_audit_hard_cap,
        "remaining_cap": remaining_cap,
    }


def remaining_provider_cap(
    provider_calls_used_today: int,
    *,
    daily_audit_hard_cap: int = DAILY_AUDIT_HARD_CAP,
) -> int:
    return max(0, daily_audit_hard_cap - provider_calls_used_today)


def _inventory_item(
    entry: CompetitionRegistryEntry,
    scope: LeagueWhitelistScope,
) -> dict[str, Any]:
    competition_id = entry.competition_id
    group = _group(competition_id, scope)
    audit_status = _audit_status(entry, scope)
    return {
        "competition_id": competition_id,
        "group": group,
        "enabled": entry.enabled,
        "season": entry.provider_mapping.get("api_football_season") or entry.season,
        "api_football_league_id": entry.provider_mapping.get("api_football_league_id", ""),
        "audit_status": audit_status,
        "audit_mode": _audit_mode(audit_status),
        "can_enable": False,
        "reason": _reason(competition_id, audit_status, scope),
        "provider_calls": 0,
        "db_reads": 0,
        "db_writes": 0,
    }


def _group(competition_id: str, scope: LeagueWhitelistScope) -> str:
    if competition_id in scope.top_five:
        return "top_five"
    if competition_id in scope.world_cup:
        return "world_cup"
    return "national_leagues"


def _audit_status(entry: CompetitionRegistryEntry, scope: LeagueWhitelistScope) -> str:
    if entry.enabled:
        return "ENABLED_EXISTING"
    if entry.competition_id in scope.in_season_national_leagues:
        return "AUDITED_IN_180"
    if entry.competition_id in scope.national_leagues_offseason:
        return "OFF_SEASON_DEFERRED"
    return "NOT_AUDITED"


def _audit_mode(audit_status: str) -> str:
    if audit_status == "AUDITED_IN_180":
        return "ENABLEMENT_AUDIT"
    return "COVERAGE_INVENTORY_AUDIT"


def _reason(
    competition_id: str,
    audit_status: str,
    scope: LeagueWhitelistScope,
) -> str:
    if audit_status == "AUDITED_IN_180":
        return "audited in prior controlled provider audit; not full whitelist completion"
    if audit_status == "ENABLED_EXISTING":
        return "already enabled; included for inventory, not a new enablement"
    if audit_status == "OFF_SEASON_DEFERRED":
        return "national league registered but excluded from in-season six-league audit"
    if competition_id in scope.top_five:
        return "top five competition registered but not covered by six-league national audit"
    return "registered whitelist competition not covered by six-league national audit"


if __name__ == "__main__":
    raise SystemExit(main())
