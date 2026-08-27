#!/usr/bin/env python3
"""Joint two-way fixed effects, bootstrapped end to end.

Protocol v5 section 4 (commit 4558f5ab).

v4 removed the home/away mean, then removed the opponent mean from that result, and
fed the leftovers to the drift model as if nothing had been estimated. One pass of
backfitting is not a joint fit, and treating fitted residuals as data understates
the uncertainty -- the generated-regressor problem. On that basis v4 called the
signal `confound-robust`, which was more than it had.

Here the two factors are fitted **jointly**, by alternating projections run to
convergence, and the whole two-stage procedure is resampled: each replication draws
teams with replacement, refits the fixed effects on the resample, and refits the
drift model to those residuals. What comes back therefore carries the cost of
having estimated the nuisance parameters.

What this still cannot do, and the report must not pretend otherwise: opponent
identity is a proxy for opponent strength and is itself measured with error; and
congestion, competition and personnel are not in the model at all. The permitted
conclusion is about what the adjustment does to the estimate, not that confounding
has been ruled out.
"""
from __future__ import annotations

import json
import os
import random
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))
import ev_se_mle as M
from _load import CORPUS, CSV, LEAGUE
from ev_se_drift_alpha import HOLDOUT_CUTOFF, parse_ts

SEED = 20260826
REPLICATIONS = 400
MAX_SWEEPS = 200
TOLERANCE = 1e-10

# (team, season, kickoff, value, side, opponent)
Row = tuple[str, str, float, float, str, str]


def rows_for(component: str) -> dict[str, list[Row]]:
    meta: dict[tuple[str, str], tuple[str, str, str, str]] = {}
    for entry in json.load(open(CORPUS))["history_rows"]:
        meta[(entry["provider_fixture_id"], entry["team_id"])] = (
            entry["provider_league_id"], entry["season"],
            entry["team_side"], entry["opponent_team_id"],
        )
    column = 4 if component == "attack" else 5
    out: dict[str, list[Row]] = {}
    for line in open(CSV):
        parts = line.rstrip("\n").split(",")
        if len(parts) != 7 or parts[0] in ("BEGIN", "ROLLBACK"):
            continue
        if parts[2] >= HOLDOUT_CUTOFF:
            continue
        found = meta.get((parts[0], parts[1]))
        if found is None:
            continue
        league = LEAGUE.get(found[0])
        if league is None:
            continue
        try:
            value = float(parts[column])
        except ValueError:
            continue
        out.setdefault(f"{league}|{component}", []).append(
            (parts[1], found[1], parse_ts(parts[2]), value, found[2], found[3])
        )
    return out


def joint_two_way_residuals(rows: list[Row]) -> list[float]:
    """Least-squares residuals from y ~ mu + side + opponent, both fitted together.

    Alternating projections on the two factor spaces converge to the joint
    least-squares fit for a two-way additive model, unlike a single sequential pass.
    The grand mean is added back so the residual series keeps the level the drift
    model expects.
    """
    values = [row[3] for row in rows]
    grand = sum(values) / len(values)
    side_effect: dict[str, float] = {}
    opponent_effect: dict[str, float] = {}
    for _ in range(MAX_SWEEPS):
        moved = 0.0
        for index, table, key in ((4, side_effect, "side"), (5, opponent_effect, "opp")):
            other = opponent_effect if key == "side" else side_effect
            other_index = 5 if key == "side" else 4
            groups: dict[str, list[float]] = {}
            for row, value in zip(rows, values, strict=True):
                partial = value - grand - other.get(str(row[other_index]), 0.0)
                groups.setdefault(str(row[index]), []).append(partial)
            for level, items in groups.items():
                new = sum(items) / len(items)
                moved = max(moved, abs(new - table.get(level, 0.0)))
                table[level] = new
        if moved < TOLERANCE:
            break
    return [
        value - side_effect.get(row[4], 0.0) - opponent_effect.get(row[5], 0.0)
        for row, value in zip(rows, values, strict=True)
    ]


def series_from(rows: list[Row], values: list[float]) -> list[list[tuple[float, float]]]:
    grouped: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for row, value in zip(rows, values, strict=True):
        grouped.setdefault((row[0], row[1]), []).append((row[2], value))
    return [sorted(s) for s in grouped.values() if len(s) >= 3]


def fit(rows: list[Row], *, adjust: bool) -> float:
    values = joint_two_way_residuals(rows) if adjust else [row[3] for row in rows]
    series = series_from(rows, values)
    if not series:
        return 0.0
    sigma2, _tau2, _ll = M.fit_full(series)
    return sigma2


def bootstrap(rows: list[Row], *, adjust: bool) -> dict[str, Any]:
    """Resample teams and refit BOTH stages, so the fixed effects cost something."""
    by_team: dict[str, list[Row]] = {}
    for row in rows:
        by_team.setdefault(row[0], []).append(row)
    teams = sorted(by_team)
    rng = random.Random(SEED)  # noqa: S311 - statistical bootstrap, not crypto
    draws: list[float] = []
    for _ in range(REPLICATIONS):
        sample: list[Row] = []
        for slot in range(len(teams)):
            picked = teams[rng.randrange(len(teams))]
            # A team drawn twice must contribute two independent series, not one
            # series with every timestamp duplicated. Tagging the clone by slot keeps
            # `series_from` grouping them apart; without it the duplicated timestamps
            # read as instantaneous jumps and the drift estimate explodes.
            sample.extend(
                (f"{row[0]}#{slot}", row[1], row[2], row[3], row[4], row[5])
                for row in by_team[picked]
            )
        draws.append(fit(sample, adjust=adjust))
    draws.sort()
    at_zero = sum(1 for d in draws if d == 0.0) / len(draws)
    return {
        "ci_low": draws[int(0.025 * len(draws))],
        "ci_high": draws[min(int(0.975 * len(draws)), len(draws) - 1)],
        "share_at_boundary": round(at_zero, 4),
        "excludes_zero": draws[int(0.025 * len(draws))] > 0.0,
    }


def report() -> dict[str, Any]:
    cells: dict[str, Any] = {}
    for component in ("attack", "defence"):
        for cell, rows in sorted(rows_for(component).items()):
            raw = fit(rows, adjust=False)
            adjusted = fit(rows, adjust=True)
            boot_raw = bootstrap(rows, adjust=False)
            boot_adj = bootstrap(rows, adjust=True)
            cells[cell] = {
                "observations": len(rows),
                "opponents": len({r[5] for r in rows}),
                "unadjusted": {"sigma2": raw, **boot_raw},
                "jointly_adjusted": {"sigma2": adjusted, **boot_adj},
                "sigma2_ratio_adjusted_over_raw": (adjusted / raw) if raw > 0 else None,
                "survives_with_nuisance_uncertainty": boot_adj["excludes_zero"],
            }
    survivors = [k for k, v in cells.items() if v["survives_with_nuisance_uncertainty"]]
    return {
        "method": (
            "joint two-way fixed effects (home/away and opponent) by alternating "
            "projections, then the local level MLE on the residuals"
        ),
        "uncertainty": (
            f"cluster bootstrap over teams, {REPLICATIONS} replications, seed {SEED}, "
            "refitting BOTH stages per replication so nuisance-parameter estimation "
            "is priced in"
        ),
        "claim_discipline": (
            "this reports what the adjustment does to the estimate. It does not "
            "establish that confounding is ruled out: opponent identity proxies "
            "opponent strength with error, and congestion, competition and personnel "
            "are absent from the model"
        ),
        "cells_whose_adjusted_interval_excludes_zero": survivors,
        "cells": cells,
    }


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, sort_keys=True))
