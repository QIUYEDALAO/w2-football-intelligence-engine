from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.league_models import LeagueProfileModel, LeagueSeasonModel


class CompetitionRegistryError(RuntimeError):
    pass


@dataclass(frozen=True, kw_only=True)
class CoverageProfile:
    xg: str
    lineups_injuries: str
    squad_value: str
    bookmaker_depth: str
    h2h: str
    settled_ah: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CoverageProfile:
        required = {"xg", "lineups_injuries", "squad_value", "bookmaker_depth", "h2h", "settled_ah"}
        missing = sorted(required - set(payload))
        if missing:
            raise CompetitionRegistryError(f"COVERAGE_PROFILE_MISSING:{','.join(missing)}")
        return cls(**{key: str(payload[key]) for key in sorted(required)})

    def as_dict(self) -> dict[str, str]:
        return {
            "xg": self.xg,
            "lineups_injuries": self.lineups_injuries,
            "squad_value": self.squad_value,
            "bookmaker_depth": self.bookmaker_depth,
            "h2h": self.h2h,
            "settled_ah": self.settled_ah,
        }


@dataclass(frozen=True, kw_only=True)
class CompetitionRegistryEntry:
    competition_id: str
    season: str
    enabled: bool
    coverage_profile: CoverageProfile
    config_path: Path
    provider_mapping: dict[str, str]
    timezone: str
    market_scope: tuple[str, ...]
    refresh_switches: dict[str, bool]
    future_refresh_policy: dict[str, Any] | None
    matchday_policy: dict[str, Any] | None
    scope_group: str
    audit_cohort: str
    audit_order: int
    config_hash: str
    profile_payload: dict[str, Any]


class CompetitionRegistry:
    """Uncached DB-backed runtime authority for competition configuration."""

    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine()

    def entries(self) -> dict[str, CompetitionRegistryEntry]:
        return self._load()

    def enabled_ids(self) -> set[str]:
        return {key for key, entry in self.entries().items() if entry.enabled}

    def require_enabled(self, competition_id: str) -> CompetitionRegistryEntry:
        entry = self.entries().get(competition_id)
        if entry is None:
            raise CompetitionRegistryError(f"COMPETITION_NOT_REGISTERED:{competition_id}")
        if not entry.enabled:
            raise CompetitionRegistryError(f"COMPETITION_NOT_ENABLED:{competition_id}")
        return entry

    def is_enabled(self, competition_id: str) -> bool:
        entry = self.entries().get(competition_id)
        return bool(entry and entry.enabled)

    def _load(self) -> dict[str, CompetitionRegistryEntry]:
        try:
            with Session(self.engine) as session:
                rows = session.execute(
                    select(LeagueProfileModel, LeagueSeasonModel)
                    .join(
                        LeagueSeasonModel,
                        LeagueSeasonModel.competition_id == LeagueProfileModel.competition_id,
                    )
                    .order_by(LeagueProfileModel.competition_id, LeagueSeasonModel.season.desc())
                ).all()
        except SQLAlchemyError as exc:
            raise CompetitionRegistryError("COMPETITION_DB_AUTHORITY_UNAVAILABLE") from exc
        entries: dict[str, CompetitionRegistryEntry] = {}
        for profile, season in rows:
            if profile.competition_id in entries:
                continue
            profile_payload = dict(profile.payload or {})
            season_payload = dict(season.payload or {})
            current_season = str(profile_payload.get("current_season") or "")
            if current_season and season.season != current_season:
                continue
            coverage = profile_payload.get("coverage_profile")
            if not isinstance(coverage, dict):
                raise CompetitionRegistryError(f"COVERAGE_PROFILE_MISSING:{profile.competition_id}")
            source = dict(profile_payload.get("install_seed") or {}).get("source") or ""
            provider_mapping = {
                str(key): str(value)
                for key, value in dict(season_payload.get("provider_mapping") or {}).items()
            } | {
                "provider": str(season_payload.get("provider") or ""),
                "api_football_league_id": str(season_payload.get("provider_league_id") or ""),
                "api_football_season": str(season_payload.get("provider_season") or season.season),
            }
            entries[profile.competition_id] = CompetitionRegistryEntry(
                competition_id=profile.competition_id,
                season=season.season,
                enabled=bool(season_payload.get("enabled") is True),
                coverage_profile=CoverageProfile.from_payload(coverage),
                config_path=Path(str(source)),
                provider_mapping=provider_mapping,
                timezone=str(season_payload.get("timezone") or "UTC"),
                market_scope=tuple(str(item) for item in season_payload.get("market_scope") or []),
                refresh_switches={
                    str(key): bool(value)
                    for key, value in dict(season_payload.get("refresh_switches") or {}).items()
                },
                future_refresh_policy=dict(season_payload["future_refresh_policy"])
                if isinstance(season_payload.get("future_refresh_policy"), dict)
                else None,
                matchday_policy=dict(season_payload["matchday_policy"])
                if isinstance(season_payload.get("matchday_policy"), dict)
                else None,
                scope_group=str(profile_payload.get("scope_group") or ""),
                audit_cohort=str(profile_payload.get("audit_cohort") or ""),
                audit_order=int(profile_payload.get("audit_order") or 999),
                config_hash=str(season_payload.get("config_hash") or ""),
                profile_payload=dict(profile_payload.get("competition_profile") or {}),
            )
        if not entries:
            raise CompetitionRegistryError("COMPETITION_DB_AUTHORITY_EMPTY")
        return entries
