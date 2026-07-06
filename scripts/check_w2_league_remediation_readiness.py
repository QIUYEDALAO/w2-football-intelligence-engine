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


def build_readiness_payload(
    *,
    provider_key_header_safe: bool = True,
    provider_quota_available: bool = True,
    provider_hard_cap_valid: bool = True,
    enabled_national_leagues_override: list[str] | None = None,
    squad_value_source_status: str = "SQUAD_VALUE_SOURCE_MISSING",
) -> dict[str, Any]:
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
    national_enabled = (
        list(enabled_national_leagues_override)
        if enabled_national_leagues_override is not None
        else [
            competition_id
            for competition_id, entry in entries.items()
            if "national_leagues" in entry.config_path.parts and entry.enabled
        ]
    )
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
    evidence_reaudit_blockers: list[str] = []
    if not provider_key_header_safe:
        evidence_reaudit_blockers.append("PROVIDER_KEY_MISSING_OR_INVALID")
    if not provider_quota_available:
        evidence_reaudit_blockers.append("PROVIDER_QUOTA_MISSING")
    if not provider_hard_cap_valid:
        evidence_reaudit_blockers.append("PROVIDER_HARD_CAP_INVALID")
    if national_enabled:
        evidence_reaudit_blockers.append("ENABLED_TRUE_NOT_ALLOWED")
    if not odds_aliases_ok:
        evidence_reaudit_blockers.append("ODDS_MARKET_MAPPING_INVALID")

    enablement_blockers: list[str] = []
    if missing_evidence:
        enablement_blockers.append("NEEDS_PROVIDER_EVIDENCE")
    if squad_value_source_status == "SQUAD_VALUE_SOURCE_MISSING":
        enablement_blockers.append("SQUAD_VALUE_SOURCE_MISSING")
    if missing_evidence or squad_value_source_status == "SQUAD_VALUE_SOURCE_MISSING":
        enablement_blockers.append("SEVEN_ITEM_AUDIT_NOT_PASSING")
    if national_enabled:
        enablement_blockers.append("ENABLED_TRUE_NOT_ALLOWED")
    if not odds_aliases_ok:
        enablement_blockers.append("ODDS_MARKET_MAPPING_INVALID")

    ready_for_evidence_reaudit = not evidence_reaudit_blockers
    ready_for_enablement_audit = not enablement_blockers
    next_provider_audit_mode = (
        "EVIDENCE_ONLY"
        if ready_for_evidence_reaudit and not ready_for_enablement_audit
        else "ENABLEMENT"
        if ready_for_enablement_audit
        else "NOT_READY"
    )
    return {
        "status": "PASS",
        "profile_validation_status": (
            "NEEDS_PROVIDER_EVIDENCE" if missing_evidence else "PASS"
        ),
        "fixture_query_status": "FIXTURES_QUERY_REVIEW_REQUIRED",
        "odds_market_mapping_status": "PASS" if odds_aliases_ok else "FAIL",
        "squad_value_source_status": squad_value_source_status,
        "ready_for_evidence_reaudit": ready_for_evidence_reaudit,
        "ready_for_enablement_audit": ready_for_enablement_audit,
        "ready_for_provider_reaudit": ready_for_evidence_reaudit,
        "next_provider_audit_mode": next_provider_audit_mode,
        "evidence_reaudit_blockers": evidence_reaudit_blockers,
        "enablement_blockers": _dedupe(enablement_blockers),
        "reason": next_provider_audit_mode,
        "evidence_only_audit_can_enable": False,
        "competitions_missing_observed_evidence": missing_evidence,
        "enabled_true": bool(national_enabled),
        "enabled_national_leagues": national_enabled,
        "provider_calls": 0,
        "db_reads": 0,
        "db_writes": 0,
    }


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


if __name__ == "__main__":
    raise SystemExit(main())
