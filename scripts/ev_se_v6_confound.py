#!/usr/bin/env python3
"""Confounding with the bootstrap p-value protocol v5 promised and did not ship.

Protocol v6 section 5 (commit b74766f9).

v5 §4 said "the interval and the bootstrap p-value". The artefact carried a
percentile interval and `share_at_boundary`, the fraction of replications resting
on the boundary. That is not a p-value. Renaming it would not have made it one, and
the honest options were to build one or to report the clause unmet.

A percentile interval does not yield a p-value at a boundary, so the construction
here is a **parametric bootstrap under the null**:

  1. fit the two-way fixed effects jointly on the real data;
  2. fit the drift model to those residuals with `sigma^2` pinned to zero, giving
     `tau^2` under the null;
  3. simulate replicates on the real timestamp geometry with no drift -- each series
     gets a constant level plus `N(0, tau^2)` noise -- and add the fitted fixed
     effects back, so a replicate has the same structure the estimator will face;
  4. refit the fixed effects jointly on each replicate and refit the drift model;
  5. `p = (1 + #{sigma2_null >= sigma2_observed}) / (1 + replications)`.

Both stages are refitted on every replicate, so the fixed effects cost something on
the null side as well as the observed side. The percentile interval and
`share_at_boundary` are retained beside it and neither is called a p-value.
"""
from __future__ import annotations

import json
import os
import random
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))
import ev_se_mle as M
import ev_se_v5_confound as V5

SEED = 20260826
REPLICATIONS = 400


def fit_effects(rows: list[V5.Row]) -> tuple[dict[str, float], dict[str, float], float]:
    """Joint two-way fixed effects, returned rather than folded into residuals."""
    values = [row[3] for row in rows]
    grand = sum(values) / len(values)
    side: dict[str, float] = {}
    opponent: dict[str, float] = {}
    for _ in range(V5.MAX_SWEEPS):
        moved = 0.0
        for index, table, other, other_index in (
            (4, side, opponent, 5), (5, opponent, side, 4)
        ):
            groups: dict[str, list[float]] = {}
            for row, value in zip(rows, values, strict=True):
                partial = value - grand - other.get(str(row[other_index]), 0.0)
                groups.setdefault(str(row[index]), []).append(partial)
            for level, items in groups.items():
                new = sum(items) / len(items)
                moved = max(moved, abs(new - table.get(level, 0.0)))
                table[level] = new
        if moved < V5.TOLERANCE:
            break
    return side, opponent, grand


def null_pvalue(rows: list[V5.Row], observed: float) -> dict[str, Any]:
    side, opponent, grand = fit_effects(rows)
    residuals = [
        row[3] - side.get(str(row[4]), 0.0) - opponent.get(str(row[5]), 0.0)
        for row in rows
    ]
    series = V5.series_from(rows, residuals)
    if not series:
        return {"status": "NOT_COMPUTABLE", "reason": "no series with three observations"}
    tau2_null, _ll = M.fit_restricted(series)

    index_by_series: dict[tuple[str, str], list[int]] = {}
    for position, row in enumerate(rows):
        index_by_series.setdefault((row[0], row[1]), []).append(position)

    rng = random.Random(SEED)  # noqa: S311 - statistical bootstrap, not crypto
    draws: list[float] = []
    for _ in range(REPLICATIONS):
        simulated = [0.0] * len(rows)
        for positions in index_by_series.values():
            level = rng.gauss(0.0, tau2_null**0.5)   # arbitrary series level, diffuse
            for position in positions:
                row = rows[position]
                simulated[position] = (
                    grand + level + rng.gauss(0.0, tau2_null**0.5)
                    + side.get(str(row[4]), 0.0)
                    + opponent.get(str(row[5]), 0.0)
                )
        replicate = [
            (row[0], row[1], row[2], simulated[position], row[4], row[5])
            for position, row in enumerate(rows)
        ]
        draws.append(V5.fit(replicate, adjust=True))
    at_least = sum(1 for d in draws if d >= observed)
    draws.sort()
    return {
        "status": "COMPUTED",
        "construction": "parametric bootstrap under sigma^2 = 0, both stages refitted",
        "replications": REPLICATIONS,
        "seed": SEED,
        "tau2_under_null": tau2_null,
        "null_draws_at_or_above_observed": at_least,
        "bootstrap_p_value": (1 + at_least) / (1 + REPLICATIONS),
        "null_distribution_p95": draws[int(0.95 * len(draws))],
        "null_share_at_boundary": round(
            sum(1 for d in draws if d == 0.0) / len(draws), 4
        ),
    }


def report() -> dict[str, Any]:
    cells: dict[str, Any] = {}
    for component in ("attack", "defence"):
        for cell, rows in sorted(V5.rows_for(component).items()):
            adjusted = V5.fit(rows, adjust=True)
            interval = V5.bootstrap(rows, adjust=True)
            cells[cell] = {
                "observations": len(rows),
                "jointly_adjusted_sigma2": adjusted,
                "percentile_interval": {
                    "ci_low": interval["ci_low"], "ci_high": interval["ci_high"],
                    "excludes_zero": interval["excludes_zero"],
                    "share_at_boundary": interval["share_at_boundary"],
                    "note": "a percentile interval; share_at_boundary is not a p-value",
                },
                "null_bootstrap": null_pvalue(rows, adjusted),
            }
    significant = [
        k for k, v in cells.items()
        if v["null_bootstrap"].get("bootstrap_p_value", 1.0) < 0.05
    ]
    entries = sorted(
        (v["null_bootstrap"].get("bootstrap_p_value", 1.0), k) for k, v in cells.items()
    )
    m = len(entries)
    floor = 1.0 / (1 + REPLICATIONS)
    largest = 0
    for i, (pv, _k) in enumerate(entries, start=1):
        if pv <= i / m * 0.05:
            largest = i
    multiplicity = {
        "tests": m,
        "smallest_attainable_p": floor,
        "bonferroni_threshold": 0.05 / m,
        "bonferroni_is_attainable": floor <= 0.05 / m,
        "resolution_note": (
            f"with {REPLICATIONS} replications the smallest p this construction can "
            f"produce is {floor:.4f}. The Bonferroni threshold across {m} tests is "
            f"{0.05 / m:.5f}, so no cell can clear it however strong the signal. "
            f"Reaching it would need at least {int(m / 0.05)} replications. This is a "
            "limit of the procedure, not evidence about football"
        ),
        "bonferroni_survivors": [k for pv, k in entries if pv <= 0.05 / m],
        "benjamini_hochberg_survivors": [k for _pv, k in entries[:largest]],
        "benjamini_hochberg_meaning": (
            "false discovery rate control: the expected proportion of false "
            "rejections among those reported is at most 5%"
        ),
        "sorted_p_values": [[k, pv] for pv, k in entries],
    }
    return {
        "multiplicity": multiplicity,
        "method": (
            "joint two-way fixed effects by alternating projections, then the local "
            "level MLE on the residuals"
        ),
        "protocol_clause": (
            "v5 section 4 required an interval AND a bootstrap p-value; v5 shipped "
            "only the interval. Both are present here"
        ),
        "claim_discipline": (
            "this reports what the adjustment does to the estimate. It does not "
            "establish that confounding is ruled out: opponent identity proxies "
            "opponent strength with error, and congestion, competition and personnel "
            "are absent from the model. These p-values carry no multiplicity "
            "correction"
        ),
        "cells_with_bootstrap_p_below_0_05": significant,
        "cells": cells,
    }


OUT = os.path.join(
    os.path.dirname(__file__), "..", "docs", "review_packages",
    "EV_SE_DRIFT_V6", "EV_SE_DRIFT_V6_CONFOUND.json",
)


if __name__ == "__main__":
    payload = {
        "schema_version": "w2.ev_se.drift_v6.confound.v1",
        "protocol_commit": "b74766f9",
        **report(),
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "wrote": OUT,
        "p_below_0_05": len(payload["cells_with_bootstrap_p_below_0_05"]),
        "benjamini_hochberg_survivors": payload["multiplicity"]["benjamini_hochberg_survivors"],
        "bonferroni_attainable": payload["multiplicity"]["bonferroni_is_attainable"],
    }))
