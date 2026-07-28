"""Runtime DB-derived W2 league whitelist audit scope."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from w2.competitions.registry import (
    CompetitionRegistry,
    CompetitionRegistryEntry,
    CompetitionRegistryError,
)


@dataclass(frozen=True)
class LeagueWhitelistScope:
    entries: Mapping[str, CompetitionRegistryEntry]
    top_five: tuple[str, ...]
    world_cup: tuple[str, ...]
    in_season_national_leagues: tuple[str, ...]
    national_leagues_offseason: tuple[str, ...]
    all_whitelist: tuple[str, ...]
    remaining_unaudited: tuple[str, ...]

    @property
    def annual_competitions(self) -> tuple[str, ...]:
        return self.all_whitelist


def load_league_whitelist_scope(
    registry: CompetitionRegistry | None = None,
) -> LeagueWhitelistScope:
    resolved_registry = registry if registry is not None else CompetitionRegistry()
    entries = resolved_registry.entries()
    if not entries:
        raise CompetitionRegistryError("COMPETITION_DB_AUTHORITY_EMPTY")

    for competition_id, entry in entries.items():
        if not competition_id or entry.competition_id != competition_id:
            raise CompetitionRegistryError("COMPETITION_SCOPE_ENTRY_MALFORMED")
        if entry.scope_group not in {"top_five", "national_leagues", "world_cup"}:
            raise CompetitionRegistryError(f"COMPETITION_SCOPE_GROUP_INVALID:{competition_id}")
        if entry.scope_group == "national_leagues" and entry.audit_cohort not in {
            "IN_SEASON",
            "OFFSEASON",
        }:
            raise CompetitionRegistryError(f"COMPETITION_AUDIT_COHORT_INVALID:{competition_id}")
        if entry.scope_group == "top_five" and entry.audit_cohort:
            raise CompetitionRegistryError(f"COMPETITION_AUDIT_COHORT_INVALID:{competition_id}")
        if (
            isinstance(entry.audit_order, bool)
            or not isinstance(entry.audit_order, int)
            or entry.audit_order < 1
            or (entry.scope_group != "world_cup" and entry.audit_order == 999)
        ):
            raise CompetitionRegistryError(f"COMPETITION_AUDIT_ORDER_INVALID:{competition_id}")

    def ordered(*, group: str | None = None, cohort: str | None = None) -> tuple[str, ...]:
        selected = [
            entry
            for entry in entries.values()
            if entry.scope_group != "world_cup"
            and (group is None or entry.scope_group == group)
            and (cohort is None or entry.audit_cohort == cohort)
        ]

        def order(entry: CompetitionRegistryEntry) -> tuple[int, int, int]:
            group_order = 0 if entry.scope_group == "top_five" else 1
            cohort_order = 0 if entry.audit_cohort == "IN_SEASON" else 1
            return (group_order, cohort_order, entry.audit_order)

        return tuple(entry.competition_id for entry in sorted(selected, key=order))

    top_five = ordered(group="top_five")
    in_season = ordered(group="national_leagues", cohort="IN_SEASON")
    offseason = ordered(group="national_leagues", cohort="OFFSEASON")
    all_whitelist = ordered()
    if not all_whitelist:
        raise CompetitionRegistryError("COMPETITION_WHITELIST_SCOPE_EMPTY")
    return LeagueWhitelistScope(
        entries=MappingProxyType(dict(entries)),
        top_five=top_five,
        world_cup=(),
        in_season_national_leagues=in_season,
        national_leagues_offseason=offseason,
        all_whitelist=all_whitelist,
        remaining_unaudited=(*top_five, *offseason),
    )
