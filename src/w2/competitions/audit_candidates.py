"""Round 2 audit-only competition descriptors.

This module is intentionally imported only by the audit CLI. Runtime registry,
scheduler, refresh, DayView, and public product paths must not import it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from w2.competitions.registry import CompetitionRegistryEntry, CoverageProfile

ROOT = Path(__file__).resolve().parents[3]
ROUND2_CANDIDATES_PATH = ROOT / "config/audit_candidates/round2_first_divisions.v1.json"
AUDIT_ONLY_IDS = (
    "belgian_pro_league",
    "turkish_super_lig",
    "greek_super_league",
    "scottish_premiership",
)


def load_round2_audit_candidates(
    path: Path = ROUND2_CANDIDATES_PATH,
    *,
    now: datetime | None = None,
) -> dict[str, CompetitionRegistryEntry]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates = payload.get("candidates")
    if payload.get("schema_version") != "w2.audit_candidates.v1" or not isinstance(
        candidates, list
    ):
        raise ValueError("AUDIT_CANDIDATE_DESCRIPTOR_SCHEMA_INVALID")
    season = str((now or datetime.now(UTC)).astimezone(UTC).year)
    entries: dict[str, CompetitionRegistryEntry] = {}
    for order, item in enumerate(candidates, start=1):
        if not isinstance(item, dict):
            raise ValueError("AUDIT_CANDIDATE_DESCRIPTOR_INVALID")
        competition_id = _required_text(item, "audit_candidate_id")
        if competition_id in entries:
            raise ValueError(f"AUDIT_CANDIDATE_DUPLICATE:{competition_id}")
        if item.get("runtime_whitelist_member") is not False:
            raise ValueError(f"AUDIT_CANDIDATE_RUNTIME_MEMBER:{competition_id}")
        if item.get("scheduler_member") is not False:
            raise ValueError(f"AUDIT_CANDIDATE_SCHEDULER_MEMBER:{competition_id}")
        if item.get("season_strategy") != "CURRENT_UTC_YEAR":
            raise ValueError(f"AUDIT_CANDIDATE_SEASON_STRATEGY_INVALID:{competition_id}")
        if any("league_id" in str(key).lower() for key in item):
            raise ValueError(f"AUDIT_CANDIDATE_GUESSED_PROVIDER_ID:{competition_id}")
        exact_names = _required_text_list(item, "provider_exact_names")
        country_aliases = _required_text_list(item, "provider_country_aliases")
        query_name = _required_text(item, "provider_query_name")
        query_country = _required_text(item, "provider_query_country")
        entries[competition_id] = CompetitionRegistryEntry(
            competition_id=competition_id,
            season=season,
            enabled=False,
            coverage_profile=CoverageProfile(
                xg="AUDIT_ONLY",
                lineups_injuries="AUDIT_ONLY",
                squad_value="LOCAL_SOURCE_ONLY",
                bookmaker_depth="AUDIT_ONLY",
                h2h="NOT_PROBED",
                settled_ah="AUDIT_ONLY",
            ),
            config_path=path,
            provider_mapping={
                "provider": _required_text(item, "provider"),
                "api_football_league_id": "",
                "api_football_season": season,
                "provider_query_name": query_name,
                "provider_query_country": query_country,
                "audit_candidate_only": "true",
            },
            timezone="UTC",
            market_scope=("AH", "OU"),
            refresh_switches={},
            future_refresh_policy=None,
            matchday_policy=None,
            scope_group="national_leagues",
            audit_cohort="IN_SEASON",
            audit_order=1000 + order,
            config_hash="",
            profile_payload={
                "name": _required_text(item, "display_name"),
                "country": _required_text(item, "country"),
                "audit_candidate_only": True,
                "runtime_whitelist_member": False,
                "scheduler_member": False,
                "provider_exact_names": exact_names,
                "provider_country_aliases": country_aliases,
                "provider_query_name": query_name,
                "provider_query_country": query_country,
            },
        )
    if tuple(entries) != AUDIT_ONLY_IDS:
        raise ValueError("AUDIT_CANDIDATE_IDENTITY_SET_INVALID")
    return entries


def is_audit_candidate(entry: CompetitionRegistryEntry) -> bool:
    return entry.profile_payload.get("audit_candidate_only") is True


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"AUDIT_CANDIDATE_FIELD_MISSING:{key}")
    return value


def _required_text_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"AUDIT_CANDIDATE_FIELD_MISSING:{key}")
    result = [str(item).strip() for item in value if str(item).strip()]
    if len(result) != len(value):
        raise ValueError(f"AUDIT_CANDIDATE_FIELD_INVALID:{key}")
    return result
