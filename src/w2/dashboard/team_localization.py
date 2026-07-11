from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

REGISTRY_PATH_ENV = "W2_TEAM_LOCALIZATION_REGISTRY_PATH"
SOURCE_REGISTRY_PATH = (
    Path(__file__).resolve().parents[3]
    / "config/team_localization/teams.zh-CN.v1.json"
)
DEFAULT_REGISTRY_PATH = Path.cwd() / "config/team_localization/teams.zh-CN.v1.json"
if not DEFAULT_REGISTRY_PATH.is_file():
    DEFAULT_REGISTRY_PATH = SOURCE_REGISTRY_PATH

LOGGER = logging.getLogger(__name__)


class TeamLocalizationRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class LocalizedTeamName:
    display_name: str
    name_zh: str | None
    provider_name: str | None
    status: str


@dataclass(frozen=True)
class _TeamEntry:
    competition_id: str
    provider_team_id: str
    provider_name: str
    name_zh: str
    aliases: tuple[str, ...]


class TeamLocalizationRegistry:
    def __init__(
        self,
        *,
        competition_aliases: dict[str, str],
        entries: list[_TeamEntry],
    ) -> None:
        self._competition_aliases = dict(competition_aliases)
        self._by_id: dict[tuple[str, str], _TeamEntry] = {}
        self._by_alias: dict[tuple[str, str], _TeamEntry] = {}
        for entry in entries:
            id_key = (entry.competition_id, entry.provider_team_id)
            if id_key in self._by_id:
                raise TeamLocalizationRegistryError(
                    f"duplicate team localization id key: {id_key}"
                )
            self._by_id[id_key] = entry
            for alias in (entry.provider_name, *entry.aliases):
                alias_key = (entry.competition_id, _normalize_name(alias))
                existing = self._by_alias.get(alias_key)
                if existing is not None and existing.provider_team_id != entry.provider_team_id:
                    raise TeamLocalizationRegistryError(
                        f"conflicting team localization alias: {alias_key}"
                    )
                self._by_alias[alias_key] = entry

    @classmethod
    def load(cls, path: Path | None = None) -> TeamLocalizationRegistry:
        path = path or team_localization_registry_path()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TeamLocalizationRegistryError(
                f"cannot load team localization registry: {path}"
            ) from exc
        if not isinstance(payload, dict):
            raise TeamLocalizationRegistryError("team localization registry must be an object")
        aliases = payload.get("competition_aliases", {})
        rows = payload.get("teams", [])
        if not isinstance(aliases, dict) or not isinstance(rows, list):
            raise TeamLocalizationRegistryError("invalid team localization registry shape")
        entries = [_parse_entry(row) for row in rows]
        return cls(
            competition_aliases={str(key): str(value) for key, value in aliases.items()},
            entries=entries,
        )

    def localize(
        self,
        *,
        competition_id: str | None,
        provider_team_id: str | None,
        provider_name: str | None,
        missing_name_fallback: str,
    ) -> LocalizedTeamName:
        provider = _optional_text(provider_name)
        competition = self._competition_aliases.get(
            _optional_text(competition_id) or "",
            _optional_text(competition_id) or "",
        )
        team_id = _optional_text(provider_team_id) or ""
        entry = self._by_id.get((competition, team_id)) if competition and team_id else None
        status = "MATCHED_BY_ID"
        if entry is None and competition and provider:
            entry = self._by_alias.get((competition, _normalize_name(provider)))
            status = "MATCHED_BY_ALIAS"
        if entry is not None:
            return LocalizedTeamName(
                display_name=entry.name_zh,
                name_zh=entry.name_zh,
                provider_name=provider or entry.provider_name,
                status=status,
            )
        if provider:
            return LocalizedTeamName(
                display_name=provider,
                name_zh=None,
                provider_name=provider,
                status="FALLBACK_PROVIDER_NAME",
            )
        return LocalizedTeamName(
            display_name=missing_name_fallback,
            name_zh=None,
            provider_name=None,
            status="MISSING_PROVIDER_NAME",
        )


def _parse_entry(value: Any) -> _TeamEntry:
    if not isinstance(value, dict):
        raise TeamLocalizationRegistryError("team localization entry must be an object")
    competition_id = _required_text(value.get("competition_id"), "competition_id")
    provider_team_id = _required_text(value.get("provider_team_id"), "provider_team_id")
    provider_name = _required_text(value.get("provider_name"), "provider_name")
    name_zh = _required_text(value.get("name_zh"), "name_zh")
    raw_aliases = value.get("aliases", [])
    if not isinstance(raw_aliases, list):
        raise TeamLocalizationRegistryError("team localization aliases must be a list")
    aliases = tuple(_required_text(alias, "alias") for alias in raw_aliases)
    return _TeamEntry(
        competition_id=competition_id,
        provider_team_id=provider_team_id,
        provider_name=provider_name,
        name_zh=name_zh,
        aliases=aliases,
    )


def _required_text(value: Any, field: str) -> str:
    text = _optional_text(value)
    if not text:
        raise TeamLocalizationRegistryError(f"blank team localization field: {field}")
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_name(value: str) -> str:
    normalized = value.casefold().replace("&", "and").replace("’", "'")
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def team_localization_registry_path() -> Path:
    configured = os.getenv(REGISTRY_PATH_ENV)
    return Path(configured) if configured else DEFAULT_REGISTRY_PATH


@lru_cache(maxsize=4)
def _load_default_registry(path: str) -> TeamLocalizationRegistry:
    try:
        return TeamLocalizationRegistry.load(Path(path))
    except TeamLocalizationRegistryError as exc:
        LOGGER.warning("team localization registry unavailable: %s", exc)
        return TeamLocalizationRegistry(competition_aliases={}, entries=[])


def default_team_localization_registry() -> TeamLocalizationRegistry:
    return _load_default_registry(str(team_localization_registry_path()))


def clear_team_localization_registry_cache() -> None:
    _load_default_registry.cache_clear()


def localize_team_name(
    *,
    competition_id: str | None,
    provider_team_id: str | None,
    provider_name: str | None,
    missing_name_fallback: str,
    registry: TeamLocalizationRegistry | None = None,
) -> LocalizedTeamName:
    active_registry = registry or default_team_localization_registry()
    return active_registry.localize(
        competition_id=competition_id,
        provider_team_id=provider_team_id,
        provider_name=provider_name,
        missing_name_fallback=missing_name_fallback,
    )
