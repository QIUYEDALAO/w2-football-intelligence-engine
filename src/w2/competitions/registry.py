from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
        required = {
            "xg",
            "lineups_injuries",
            "squad_value",
            "bookmaker_depth",
            "h2h",
            "settled_ah",
        }
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


class CompetitionRegistry:
    def __init__(self, root: Path = Path("config/competitions")) -> None:
        self.root = root
        self._entries: dict[str, CompetitionRegistryEntry] | None = None

    def entries(self) -> dict[str, CompetitionRegistryEntry]:
        if self._entries is None:
            self._entries = self._load()
        return self._entries

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
        if not self.root.exists():
            raise CompetitionRegistryError(f"COMPETITION_CONFIG_ROOT_MISSING:{self.root}")
        entries: dict[str, CompetitionRegistryEntry] = {}
        staging_enabled_ids = _staging_enabled_competition_ids()
        for path in sorted(self.root.rglob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            competition_id = str(payload.get("competition_id") or "")
            if not competition_id:
                raise CompetitionRegistryError(f"COMPETITION_ID_MISSING:{path}")
            if competition_id in entries:
                raise CompetitionRegistryError(f"COMPETITION_DUPLICATE:{competition_id}")
            coverage = payload.get("coverage_profile")
            if not isinstance(coverage, dict):
                raise CompetitionRegistryError(f"COVERAGE_PROFILE_MISSING:{competition_id}")
            enabled = bool(payload.get("enabled") is True)
            if competition_id in staging_enabled_ids:
                enabled = True
            entries[competition_id] = CompetitionRegistryEntry(
                competition_id=competition_id,
                season=str(payload.get("season") or ""),
                enabled=enabled,
                coverage_profile=CoverageProfile.from_payload(coverage),
                config_path=path,
                provider_mapping={
                    str(key): str(value)
                    for key, value in (payload.get("provider_mapping") or {}).items()
                }
                if isinstance(payload.get("provider_mapping"), dict)
                else {},
            )
        missing_staging = sorted(staging_enabled_ids - set(entries))
        if missing_staging:
            raise CompetitionRegistryError(
                f"STAGING_ENABLED_COMPETITION_NOT_REGISTERED:{','.join(missing_staging)}"
            )
        return entries


def _staging_enabled_competition_ids() -> set[str]:
    raw = os.environ.get("W2_STAGING_ENABLED_COMPETITIONS", "")
    if not raw.strip():
        return set()
    environment = os.environ.get("W2_ENVIRONMENT", "").strip().lower()
    if environment != "staging":
        return set()
    return {item.strip() for item in raw.split(",") if item.strip()}
