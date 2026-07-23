"""DB-derived W2 league whitelist audit scope (no league IDs are hard-coded here)."""

from __future__ import annotations

from w2.competitions.registry import CompetitionRegistry


def _scope(*, group: str | None = None, cohort: str | None = None) -> tuple[str, ...]:
    entries = CompetitionRegistry().entries().values()
    selected = [
        entry
        for entry in entries
        if (group is None or entry.scope_group == group)
        and (cohort is None or entry.audit_cohort == cohort)
        and entry.scope_group != "world_cup"
    ]

    def order(entry):  # type: ignore[no-untyped-def]
        group_order = 0 if entry.scope_group == "top_five" else 1
        cohort_order = 0 if entry.audit_cohort == "IN_SEASON" else 1
        return (group_order, cohort_order, entry.audit_order)

    return tuple(entry.competition_id for entry in sorted(selected, key=order))


TOP_FIVE_COMPETITIONS = _scope(group="top_five")
WORLD_CUP_COMPETITIONS: tuple[str, ...] = ()
IN_SEASON_NATIONAL_LEAGUES = _scope(group="national_leagues", cohort="IN_SEASON")
NATIONAL_LEAGUES_OFFSEASON = _scope(group="national_leagues", cohort="OFFSEASON")
ALL_WHITELIST_COMPETITIONS = _scope()
REMAINING_UNAUDITED_WHITELIST = (*TOP_FIVE_COMPETITIONS, *NATIONAL_LEAGUES_OFFSEASON)
