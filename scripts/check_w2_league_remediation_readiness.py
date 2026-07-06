from __future__ import annotations

import argparse
import json
from typing import Any

from w2.competitions.league_profile_validation import validate_league_profile_mapping
from w2.competitions.league_whitelist_scope import ALL_WHITELIST_COMPETITIONS
from w2.competitions.odds_market_mapping import normalize_market_name
from w2.competitions.registry import CompetitionRegistry


def main() -> int:
    parser = argparse.ArgumentParser(description="Check offline W2 league remediation readiness.")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    payload = build_readiness_payload()
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["status"] == "PASS" else 1


def build_readiness_payload() -> dict[str, Any]:
    registry = CompetitionRegistry()
    entries = registry.entries()
    profile_results = [
        validate_league_profile_mapping(entries[competition_id], {}).as_dict()
        for competition_id in ALL_WHITELIST_COMPETITIONS
    ]
    missing_evidence = [
        result["competition_id"]
        for result in profile_results
        if result["status"] == "NEEDS_PROVIDER_EVIDENCE"
    ]
    national_enabled = [
        competition_id
        for competition_id, entry in entries.items()
        if "national_leagues" in entry.config_path.parts and entry.enabled
    ]
    odds_aliases_ok = all(
        normalize_market_name(name) == expected
        for name, expected in {
            "Asian Handicap": "AH",
            "Handicap Result": "AH",
            "Asian Handicap First Half": "AH",
            "Goals Over/Under": "OU",
            "Over/Under": "OU",
            "Total Goals": "OU",
            "Match Goals": "OU",
        }.items()
    )
    squad_value_status = "SQUAD_VALUE_SOURCE_MISSING"
    ready = not missing_evidence and odds_aliases_ok and not national_enabled
    reason = "READY" if ready else "NEEDS_PROVIDER_EVIDENCE"
    if squad_value_status == "SQUAD_VALUE_SOURCE_MISSING":
        ready = False
        reason = "SQUAD_VALUE_SOURCE_MISSING"
    return {
        "status": "PASS",
        "profile_validation_status": (
            "NEEDS_PROVIDER_EVIDENCE" if missing_evidence else "PASS"
        ),
        "fixture_query_status": "FIXTURES_QUERY_REVIEW_REQUIRED",
        "odds_market_mapping_status": "PASS" if odds_aliases_ok else "FAIL",
        "squad_value_source_status": squad_value_status,
        "ready_for_provider_reaudit": ready,
        "reason": reason,
        "competitions_missing_observed_evidence": missing_evidence,
        "enabled_true": bool(national_enabled),
        "enabled_national_leagues": national_enabled,
        "provider_calls": 0,
        "db_reads": 0,
        "db_writes": 0,
    }


if __name__ == "__main__":
    raise SystemExit(main())
