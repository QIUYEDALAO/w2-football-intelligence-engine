from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.league_models import (
    LeagueProfileModel,
    LeagueReadinessAuditModel,
    LeagueSeasonModel,
)

SEED_SCHEMA_VERSION = "w2.competition_runtime_authority.v1"


@dataclass(frozen=True, kw_only=True)
class CompetitionSeedReport:
    inserted_profiles: int = 0
    updated_profiles: int = 0
    inserted_seasons: int = 0
    updated_seasons: int = 0
    unchanged: int = 0
    audits_written: int = 0
    conflicts: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "w2.competition_seed_report.v1",
            "inserted_profiles": self.inserted_profiles,
            "updated_profiles": self.updated_profiles,
            "inserted_seasons": self.inserted_seasons,
            "updated_seasons": self.updated_seasons,
            "unchanged": self.unchanged,
            "audits_written": self.audits_written,
            "conflicts": list(self.conflicts),
        }


def seed_competition_runtime_authority(
    bind: Engine | Connection,
    *,
    config_root: Path = Path("config"),
    environment: str = "production",
    updated_by: str = "arch-p0-03-first-install-seed",
    now: datetime | None = None,
) -> CompetitionSeedReport:
    """Idempotently import install-time JSON into the DB runtime authority."""
    current = now or datetime.now(UTC)
    competition_root = config_root / "competitions"
    future_payload = _read_json(config_root / "policies/future_fixture_refresh.v1.json")
    matchday_payload = _read_json(config_root / "policies/matchday_intake.v2.json")
    future_by_id = _policy_by_competition(future_payload)
    matchday_by_id = _policy_by_competition(matchday_payload)
    profile_inputs = [
        _read_json(path) | {"_config_path": str(path)}
        for path in sorted(competition_root.rglob("*.json"))
    ]
    conflicts = _mapping_conflicts(profile_inputs, future_by_id, matchday_by_id)
    if conflicts:
        return CompetitionSeedReport(conflicts=tuple(conflicts))

    counters = {
        "inserted_profiles": 0,
        "updated_profiles": 0,
        "inserted_seasons": 0,
        "updated_seasons": 0,
        "unchanged": 0,
        "audits_written": 0,
    }
    with Session(bind=bind) as session:
        for source in profile_inputs:
            competition_id = str(source.get("competition_id") or "")
            season = str(source.get("season") or "")
            if not competition_id or not season:
                raise ValueError(f"COMPETITION_SEED_IDENTITY_MISSING:{source['_config_path']}")
            future = future_by_id.get(competition_id)
            matchday = matchday_by_id.get(competition_id)
            enabled = bool(source.get("enabled") is True)
            if environment.strip().lower() == "staging":
                enabled = (
                    enabled
                    or bool((future or {}).get("enabled") is True)
                    or bool((matchday or {}).get("enabled") is True)
                )
            provider_mapping = dict(source.get("provider_mapping") or {})
            provider = str((future or matchday or {}).get("provider") or "api_football")
            provider_league_id = str(
                (future or matchday or {}).get("provider_league_id")
                or provider_mapping.get("api_football_league_id")
                or ""
            )
            provider_season = str(
                (future or matchday or {}).get("season")
                or provider_mapping.get("api_football_season")
                or season
            )
            config_path = Path(str(source["_config_path"]))
            scope_group = (
                config_path.parent.name if config_path.parent != competition_root else "world_cup"
            )
            profile_core = {
                "schema_version": SEED_SCHEMA_VERSION,
                "competition_profile": {
                    key: value for key, value in source.items() if key != "_config_path"
                },
                "current_season": season,
                "timezone": source.get("timezone"),
                "market_scope": list(source.get("market_scope") or []),
                "coverage_profile": dict(source.get("coverage_profile") or {}),
                "scope_group": scope_group,
                "audit_cohort": source.get("audit_cohort"),
                "audit_order": source.get("audit_order"),
                "install_seed": {
                    "source": str(config_path),
                    "source_version": source.get("version"),
                },
            }
            season_core = {
                "schema_version": SEED_SCHEMA_VERSION,
                "environment": environment.strip().lower(),
                "enabled": enabled,
                "provider": provider,
                "provider_league_id": provider_league_id,
                "provider_season": provider_season,
                "provider_mapping": provider_mapping,
                "timezone": source.get("timezone"),
                "market_scope": list(source.get("market_scope") or []),
                "refresh_switches": {
                    "fixtures": bool((future or {}).get("enabled") is True),
                    "odds": bool((matchday or {}).get("enabled") is True),
                    "lineups": bool((matchday or {}).get("enabled") is True),
                },
                "future_refresh_policy": future,
                "matchday_policy": matchday,
                "install_seed": {
                    "competition_source": str(config_path),
                    "future_policy_version": future_payload.get("version"),
                    "matchday_policy_version": matchday_payload.get("version"),
                },
            }
            profile_hash = _hash(profile_core)
            season_hash = _hash(season_core)
            profile_payload = profile_core | {
                "config_hash": profile_hash,
                "updated_by": updated_by,
                "updated_at": current.isoformat(),
            }
            season_payload = season_core | {
                "config_hash": season_hash,
                "updated_by": updated_by,
                "updated_at": current.isoformat(),
            }
            profile = session.scalar(
                select(LeagueProfileModel).where(
                    LeagueProfileModel.competition_id == competition_id
                )
            )
            profile_changed = profile is None
            if profile is None:
                profile = LeagueProfileModel(
                    competition_id=competition_id,
                    name=str(source.get("name") or competition_id),
                    country=str(source.get("country") or "International"),
                    payload=profile_payload,
                )
                session.add(profile)
                counters["inserted_profiles"] += 1

            season_row = session.scalar(
                select(LeagueSeasonModel).where(
                    LeagueSeasonModel.competition_id == competition_id,
                    LeagueSeasonModel.season == season,
                )
            )
            season_changed = season_row is None
            if season_row is None:
                season_row = LeagueSeasonModel(
                    competition_id=competition_id,
                    season=season,
                    lifecycle="ACTIVE" if enabled else "CONFIGURED",
                    payload=season_payload,
                )
                session.add(season_row)
                counters["inserted_seasons"] += 1
            if not profile_changed and not season_changed:
                counters["unchanged"] += 1
                continue
            audit_payload = {
                "schema_version": "w2.competition_config_audit.v1",
                "action": "FIRST_INSTALL_SEED",
                "competition_id": competition_id,
                "season": season,
                "environment": environment.strip().lower(),
                "enabled": enabled,
                "profile_hash": profile_hash,
                "season_hash": season_hash,
                "updated_by": updated_by,
                "updated_at": current.isoformat(),
            }
            audit_hash = _hash(audit_payload)
            existing_audit = session.scalar(
                select(LeagueReadinessAuditModel).where(
                    LeagueReadinessAuditModel.competition_id == competition_id,
                    LeagueReadinessAuditModel.audit_sha256 == audit_hash,
                )
            )
            if existing_audit is None:
                session.add(
                    LeagueReadinessAuditModel(
                        competition_id=competition_id,
                        audit_sha256=audit_hash,
                        created_at=current,
                        payload=audit_payload,
                    )
                )
                counters["audits_written"] += 1
        session.commit()
    return CompetitionSeedReport(conflicts=(), **counters)


def set_competition_enabled(
    bind: Engine | Connection,
    *,
    competition_id: str,
    enabled: bool,
    updated_by: str,
    now: datetime | None = None,
) -> str:
    """Audited operational update used by operators; no build or deploy is involved."""
    current = now or datetime.now(UTC)
    with Session(bind=bind) as session:
        profile = session.scalar(
            select(LeagueProfileModel).where(LeagueProfileModel.competition_id == competition_id)
        )
        if profile is None:
            raise ValueError(f"COMPETITION_NOT_REGISTERED:{competition_id}")
        season = str(profile.payload.get("current_season") or "")
        row = session.scalar(
            select(LeagueSeasonModel).where(
                LeagueSeasonModel.competition_id == competition_id,
                LeagueSeasonModel.season == season,
            )
        )
        if row is None:
            raise ValueError(f"COMPETITION_SEASON_NOT_REGISTERED:{competition_id}:{season}")
        payload = dict(row.payload)
        previous = bool(payload.get("enabled") is True)
        payload["enabled"] = enabled
        payload["updated_by"] = updated_by
        payload["updated_at"] = current.isoformat()
        hash_input = {
            key: value
            for key, value in payload.items()
            if key not in {"config_hash", "updated_at", "updated_by"}
        }
        payload["config_hash"] = _hash(hash_input)
        row.payload = payload
        row.lifecycle = "ACTIVE" if enabled else "CONFIGURED"
        audit_payload = {
            "schema_version": "w2.competition_config_audit.v1",
            "action": "SET_ENABLED",
            "competition_id": competition_id,
            "season": season,
            "before": previous,
            "after": enabled,
            "updated_by": updated_by,
            "updated_at": current.isoformat(),
        }
        audit_hash = _hash(audit_payload)
        session.add(
            LeagueReadinessAuditModel(
                competition_id=competition_id,
                audit_sha256=audit_hash,
                created_at=current,
                payload=audit_payload,
            )
        )
        session.commit()
        return audit_hash


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"COMPETITION_SEED_JSON_INVALID:{path}")
    return payload


def _policy_by_competition(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["competition_id"]): dict(item)
        for item in payload.get("competitions", [])
        if isinstance(item, dict) and item.get("competition_id")
    }


def _mapping_conflicts(
    profiles: list[dict[str, Any]],
    future_by_id: dict[str, dict[str, Any]],
    matchday_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    conflicts: list[str] = []
    for profile in profiles:
        competition_id = str(profile.get("competition_id") or "")
        mapping = dict(profile.get("provider_mapping") or {})
        values = {
            str(value)
            for value in (
                mapping.get("api_football_league_id"),
                (future_by_id.get(competition_id) or {}).get("provider_league_id"),
                (matchday_by_id.get(competition_id) or {}).get("provider_league_id"),
            )
            if value not in (None, "")
        }
        seasons = {
            str(value)
            for value in (
                profile.get("season"),
                mapping.get("api_football_season"),
                (future_by_id.get(competition_id) or {}).get("season"),
                (matchday_by_id.get(competition_id) or {}).get("season"),
            )
            if value not in (None, "")
        }
        if len(values) > 1:
            conflicts.append(
                f"PROVIDER_LEAGUE_ID_CONFLICT:{competition_id}:{','.join(sorted(values))}"
            )
        if len(seasons) > 1:
            conflicts.append(
                f"PROVIDER_SEASON_CONFLICT:{competition_id}:{','.join(sorted(seasons))}"
            )
    return conflicts


def _hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
