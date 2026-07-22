"""Canonical W2 league whitelist audit scope."""

from __future__ import annotations

TOP_FIVE_COMPETITIONS = (
    "premier_league",
    "la_liga",
    "bundesliga",
    "serie_a",
    "ligue_1",
)
# Tournament football is deliberately outside the current W2 league whitelist:
# its one-off format is not in scope for the league-calibrated workflow.
WORLD_CUP_COMPETITIONS: tuple[str, ...] = ()
IN_SEASON_NATIONAL_LEAGUES = (
    "brasileirao_serie_a",
    "argentina_primera",
    "mls",
    "chinese_super_league",
    "allsvenskan",
    "eliteserien",
)
NATIONAL_LEAGUES_OFFSEASON = ("eredivisie", "primeira_liga")
ALL_WHITELIST_COMPETITIONS = (
    *TOP_FIVE_COMPETITIONS,
    *WORLD_CUP_COMPETITIONS,
    *IN_SEASON_NATIONAL_LEAGUES,
    *NATIONAL_LEAGUES_OFFSEASON,
)
REMAINING_UNAUDITED_WHITELIST = (
    *TOP_FIVE_COMPETITIONS,
    *WORLD_CUP_COMPETITIONS,
    *NATIONAL_LEAGUES_OFFSEASON,
)
