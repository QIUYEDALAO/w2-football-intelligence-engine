#!/usr/bin/env python3
"""The one evaluation-window constructor, plus a check that catches season resets.

Protocol v5 section 3 (commit 4558f5ab).

Production takes the latest 20 rows for a team ordered by kickoff **across
seasons** -- `team_xg_matches_for_teams` has a `limit_per_team` and no season
predicate -- and then drops rows with `kickoff >= as_of` or `captured_at > as_of`
in `_xg_uncertainty_rows`.

v4 rebuilt that window three times and got it wrong twice. `production_state_ages`
and `se0_squared_quantiles` both grouped by `(league, team, season)`, so every
window sat inside one season and never spanned an off-season break. The reported
age span came out four to fifteen times too narrow, which was the foundation of
v4's recommendation. Everything that needs an evaluation state now calls this
module, and `self_check` fails if a season-reset construction is ever mistaken for
this one.

    python3 scripts/ev_se_v5_window.py     # runs the self-check
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))
from _load import CORPUS, CSV, LEAGUE
from ev_se_drift_alpha import HOLDOUT_CUTOFF, parse_ts

DENOMINATOR = 20
MIN_OBSERVED = 3          # production fails closed below three

# (kickoff_days, value, fixture_id, captured_at_days)
Observation = tuple[float, float, str, float]


def observed_timelines(component: str) -> dict[tuple[str, str], list[Observation]]:
    """(league, team) -> the team's xG rows, kickoff-ordered, seasons run together.

    This mirrors what `team_xg_match` holds and how production orders it. No season
    key appears anywhere in this function, which is the point.
    """
    column = 4 if component == "attack" else 5
    league_of: dict[tuple[str, str], str] = {}
    for row in json.load(open(CORPUS))["history_rows"]:
        league = LEAGUE.get(row["provider_league_id"])
        if league is not None:
            league_of[(row["provider_fixture_id"], row["team_id"])] = league

    out: dict[tuple[str, str], list[Observation]] = {}
    for line in open(CSV):
        parts = line.rstrip("\n").split(",")
        if len(parts) != 7 or parts[0] in ("BEGIN", "ROLLBACK"):
            continue
        if parts[2] >= HOLDOUT_CUTOFF:
            continue
        league = league_of.get((parts[0], parts[1]))
        if league is None:
            continue
        try:
            value = float(parts[column])
        except ValueError:
            continue
        out.setdefault((league, parts[1]), []).append(
            (parse_ts(parts[2]), value, parts[0], parse_ts(parts[3]))
        )
    for series in out.values():
        series.sort()
    return out


def expected_timelines() -> dict[tuple[str, str], list[tuple[float, str]]]:
    """(league, team) -> every finished fixture, kickoff-ordered, seasons run together."""
    out: dict[tuple[str, str], list[tuple[float, str]]] = {}
    for row in json.load(open(CORPUS))["history_rows"]:
        league = LEAGUE.get(row["provider_league_id"])
        if league is None or row["kickoff_utc"] >= HOLDOUT_CUTOFF:
            continue
        out.setdefault((league, row["team_id"]), []).append(
            (parse_ts(row["kickoff_utc"]), row["provider_fixture_id"])
        )
    for series in out.values():
        series.sort()
    return out


def observed_states(
    component: str, *, pit: bool = False, season_reset: bool = False
) -> dict[str, list[dict[str, Any]]]:
    """Evaluation states on production's window.

    `season_reset` exists only so `self_check` can build the wrong thing on purpose
    and prove the check notices. Nothing else may pass it.
    """
    if season_reset:
        timelines: dict[tuple[str, ...], list[Observation]] = {}
        seasons: dict[tuple[str, str], str] = {}
        for row in json.load(open(CORPUS))["history_rows"]:
            seasons[(row["provider_fixture_id"], row["team_id"])] = row["season"]
        for (league, team), series in observed_timelines(component).items():
            for observation in series:
                season = seasons.get((observation[2], team), "?")
                timelines.setdefault((league, team, season), []).append(observation)
        for series in timelines.values():
            series.sort()
        source: dict[Any, list[Observation]] = dict(timelines)
    else:
        source = dict(observed_timelines(component))

    out: dict[str, list[dict[str, Any]]] = {}
    for key, series in source.items():
        league = key[0]
        for index in range(DENOMINATOR, len(series)):
            as_of, actual, _fixture, _seen = series[index]
            window = series[index - DENOMINATOR : index]
            if pit:
                window = [row for row in window if row[3] <= as_of]
            if len(window) < MIN_OBSERVED:
                continue
            values = [row[1] for row in window]
            n = len(values)
            mean = sum(values) / n
            variance = sum((v - mean) ** 2 for v in values) / (n - 1)
            if variance <= 0:
                continue
            out.setdefault(f"{league}|{component}", []).append(
                {
                    "mean_age_days": sum(as_of - row[0] for row in window) / n,
                    "se0_squared": variance / n,
                    "residual": actual - mean,
                    "observed": n,
                }
            )
    return out


def coverage_states(
    component: str, *, pit: bool = False
) -> dict[str, list[dict[str, Any]]]:
    """Evaluation states carrying real coverage, on the same cross-season window.

    `E` is the latest 20 **expected** fixtures from the frozen corpus; `O` is the
    subset carrying xG, and under `pit` the subset whose capture time is at or
    before the epoch. Coverage is |O|/|E| and varies, which is what makes a coverage
    stratification mean anything.
    """
    values: dict[tuple[str, str], tuple[float, float]] = {}
    for (_league, team), series in observed_timelines(component).items():
        for _kickoff, value, fixture, seen in series:
            values[(fixture, team)] = (value, seen)
    out: dict[str, list[dict[str, Any]]] = {}
    for (league, team), timeline in expected_timelines().items():
        for index in range(DENOMINATOR, len(timeline)):
            as_of, target = timeline[index]
            actual = values.get((target, team))
            if actual is None:
                continue
            observed: list[tuple[float, float]] = []
            for kickoff, fixture in timeline[index - DENOMINATOR : index]:
                found = values.get((fixture, team))
                if found is None:
                    continue
                if pit and found[1] > as_of:
                    continue
                observed.append((kickoff, found[0]))
            if len(observed) < MIN_OBSERVED:
                continue
            sample = [v for _, v in observed]
            n = len(sample)
            mean = sum(sample) / n
            variance = sum((v - mean) ** 2 for v in sample) / (n - 1)
            if variance <= 0:
                continue
            out.setdefault(f"{league}|{component}", []).append(
                {
                    "mean_age_days": sum(as_of - k for k, _ in observed) / n,
                    "coverage": n / DENOMINATOR,
                    "se0_squared": variance / n,
                    "residual": actual[0] - mean,
                }
            )
    return out


def self_check() -> dict[str, Any]:
    """Fail if the cross-season window is indistinguishable from a season-reset one.

    A season reset can only shorten a window's calendar reach: it discards the older
    fixtures that sit on the far side of a break. So the reset construction must
    produce both fewer states and a narrower age spread. If a future refactor
    reintroduces the season key, these two stop differing and this check fails.
    """
    findings: list[str] = []
    cross = observed_states("attack")
    reset = observed_states("attack", season_reset=True)
    cross_n = sum(len(v) for v in cross.values())
    reset_n = sum(len(v) for v in reset.values())

    def spread(states: dict[str, list[dict[str, Any]]]) -> float:
        ages = sorted(s["mean_age_days"] for v in states.values() for s in v)
        if not ages:
            return 0.0
        return float(ages[int(0.9 * len(ages))] - ages[int(0.1 * len(ages))])

    cross_spread, reset_spread = spread(cross), spread(reset)
    if cross_n <= reset_n:
        findings.append("cross_season_window_produced_no_more_states_than_a_reset")
    if cross_spread <= reset_spread * 1.5:
        findings.append("cross_season_age_spread_not_materially_wider_than_a_reset")
    if any("season" in str(k) for k in observed_timelines("attack")):
        findings.append("season_key_leaked_into_the_production_timeline")
    return {
        "cross_season_states": cross_n,
        "season_reset_states": reset_n,
        "cross_season_age_spread_p10_p90_days": round(cross_spread, 3),
        "season_reset_age_spread_p10_p90_days": round(reset_spread, 3),
        "spread_ratio": round(cross_spread / reset_spread, 3) if reset_spread else None,
        "findings": findings,
        "result": "PASS" if not findings else "FAIL",
    }


def prove_check_bites() -> dict[str, Any]:
    """Negative control: make the production constructor reset by season and confirm
    `self_check` fails. A guard nobody has seen fail is not a guard."""
    # Patch this module's own globals. Reaching for `import ev_se_v5_window` here
    # binds a second module object when the file runs as __main__, and the patch
    # then lands somewhere `self_check` never looks -- which is how this negative
    # control first reported a pass while injecting nothing.
    scope = globals()
    original = scope["observed_states"]
    scope["observed_states"] = (
        lambda component, *, pit=False, season_reset=False: original(
            component, pit=pit, season_reset=True
        )
    )
    try:
        broken = self_check()
    finally:
        scope["observed_states"] = original
    return {
        "injected_regression": "production constructor forced to group by season",
        "self_check_result": broken["result"],
        "findings": broken["findings"],
        "guard_bites": broken["result"] == "FAIL",
    }


if __name__ == "__main__":
    if "--prove-it-fails" in sys.argv:
        proof = prove_check_bites()
        print(json.dumps(proof, indent=2, sort_keys=True))
        raise SystemExit(0 if proof["guard_bites"] else 1)
    report = self_check()
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["result"] == "PASS" else 1)
