#!/usr/bin/env python3
"""Representative-geometry power and the operational impact of an age term.

Protocol v4 section 7 (commit 18f812b7). v3 produced both of these numbers in an
ad-hoc shell heredoc, so neither could be reproduced, and its report mixed three
different populations inside one paragraph. This script is the committed source
for both, and it names the population for every number it emits.

  representative_geometry -- the synthetic 20 teams x 45 matches / 300 days design
  production_states       -- the distribution of window ages across real evaluation
                             states, which is what an age term would actually see

The third population, `real_cell_geometry`, is the per-cell power study and lives
in its own artefact, EV_SE_DRIFT_V4_POWER.json.
"""
from __future__ import annotations

import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from typing import Any

import ev_se_mle as M
import ev_se_variogram as V
from _load import load
from ev_se_beta_kappa import DENOMINATOR

SEED = 20260826
REPLICATIONS = 500
SIGMA2_GRID = (0.0, 1e-5, 3e-5, 1e-4, 3e-4, 1e-3)
TEAMS, MATCHES, SPAN, TAU2 = 20, 45, 300.0, 0.5
OUT = os.path.join(
    os.path.dirname(__file__), "..", "docs", "review_packages",
    "EV_SE_DRIFT_V4", "EV_SE_DRIFT_V4_IMPACT.json",
)


def draw(rng: random.Random, sigma2: float) -> list[list[tuple[float, float]]]:
    out = []
    for _ in range(TEAMS):
        times = sorted(rng.uniform(0.0, SPAN) for _ in range(MATCHES))
        level, prev, series = 0.0, times[0], []
        for t in times:
            if t > prev:
                level += rng.gauss(0.0, math.sqrt(sigma2 * (t - prev)))
            series.append((t, level + rng.gauss(0.0, math.sqrt(TAU2))))
            prev = t
        out.append(series)
    return out


def variogram_detects(replicate: list[list[tuple[float, float]]]) -> bool:
    rows = []
    for i, series in enumerate(replicate):
        for a in range(len(series)):
            ta, ya = series[a]
            for b in range(a + 1, len(series)):
                tb, yb = series[b]
                rows.append((str(i), tb - ta, (yb - ya) ** 2))
    lo, _hi = V.bootstrap(V.team_stats(rows))
    return lo is not None and lo > 0.0


def representative_power() -> dict[str, Any]:
    grid: dict[str, Any] = {}
    for sigma2 in SIGMA2_GRID:
        rng = random.Random(SEED)  # noqa: S311 - statistical replication, not crypto
        mle_hits = var_hits = 0
        for _ in range(REPLICATIONS):
            replicate = draw(rng, sigma2)
            _s, _t, ll_full = M.fit_full(replicate)
            _tr, ll_null = M.fit_restricted(replicate)
            if M.lrt_pvalue(ll_full, ll_null) < 0.05:
                mle_hits += 1
            if variogram_detects(replicate):
                var_hits += 1
        grid[f"{sigma2:.1e}"] = {
            "mle_rejection_rate": mle_hits / REPLICATIONS,
            "variogram_rejection_rate": var_hits / REPLICATIONS,
        }
        print(f"  sigma2={sigma2:.1e} mle={mle_hits / REPLICATIONS:.3f} "
              f"vario={var_hits / REPLICATIONS:.3f}", flush=True)
    size = grid["0.0e+00"]["mle_rejection_rate"]
    return {
        "population": "representative_geometry",
        "design": f"{TEAMS} teams x {MATCHES} matches / {SPAN:.0f} days, tau2={TAU2}",
        "replications": REPLICATIONS,
        "seed": SEED,
        "grid": grid,
        "mle_size_at_null": size,
        "size_verdict": "CALIBRATED" if size <= 0.08 else "TEST_MISCALIBRATED",
        "note": (
            "this is a synthetic design, not any real league; per-cell power on real "
            "timestamp geometry is a separate population in EV_SE_DRIFT_V4_POWER.json"
        ),
    }


def production_state_ages() -> dict[str, Any]:
    """Window age across real evaluation states -- the range an age term would see."""
    cells: dict[str, list[float]] = {}
    for component in ("attack", "defence"):
        for (league, _team, _season), series in load(component).items():
            s = sorted(series)
            for i in range(DENOMINATOR, len(s)):
                as_of = s[i][0]
                window = s[i - DENOMINATOR : i]
                cells.setdefault(f"{league}|{component}", []).append(
                    sum(as_of - t for t, _ in window) / DENOMINATOR
                )
    out: dict[str, Any] = {}
    for cell, ages in sorted(cells.items()):
        ages.sort()
        n = len(ages)
        out[cell] = {
            "states": n,
            "age_p10_days": round(ages[int(0.10 * n)], 3),
            "age_p50_days": round(ages[int(0.50 * n)], 3),
            "age_p90_days": round(ages[int(0.90 * n)], 3),
            "age_p10_to_p90_span_days": round(ages[int(0.90 * n)] - ages[int(0.10 * n)], 3),
        }
    return {"population": "production_states", "cells": out}


def age_term_impact(ages: dict[str, Any], evidence_path: str) -> dict[str, Any]:
    """SE ratio between the 10th and 90th percentile of realised age, per cell.

    Uses each cell's own alpha point estimate and its own median SE0^2. This is the
    size of the correction an age term would apply in production, as distinct from
    the size of the effect the estimator can detect.
    """
    with open(evidence_path, encoding="utf-8") as fh:
        evidence = json.load(fh)
    out: dict[str, Any] = {}
    for cell, stats in ages["cells"].items():
        alpha = evidence["alpha_cells"][cell]["mle"]["sigma2_alpha_abs"]
        se0sq = evidence["form_mismatch"][cell]["se0_squared_p50"]
        lo = (se0sq + alpha * stats["age_p10_days"]) ** 0.5
        hi = (se0sq + alpha * stats["age_p90_days"]) ** 0.5
        out[cell] = {
            "alpha_abs": alpha,
            "se0_squared_p50": se0sq,
            "se_ratio_p90_over_p10": round(hi / lo, 6),
            "se_percent_change": round((hi / lo - 1.0) * 100.0, 4),
        }
    ratios = [v["se_percent_change"] for v in out.values()]
    ratios_sorted = sorted(ratios)
    return {
        "population": "production_states",
        "basis": "each cell's own alpha point estimate and median SE0^2",
        "cells": out,
        "max_percent_change": max(ratios),
        "median_percent_change": ratios_sorted[len(ratios_sorted) // 2],
        "cells_with_zero_change": sum(1 for r in ratios if r == 0.0),
        "cells_total": len(ratios),
    }


def main() -> int:
    print("representative geometry power:")
    power = representative_power()
    ages = production_state_ages()
    evidence = os.path.join(
        os.path.dirname(__file__), "..", "docs", "review_packages",
        "EV_SE_DRIFT_V3", "EV_SE_DRIFT_V3_EVIDENCE.json",
    )
    impact = age_term_impact(ages, evidence)
    payload = {
        "schema_version": "w2.ev_se.drift_v4.impact.v1",
        "protocol_commit": "18f812b7",
        "populations_are_never_mixed": [
            "representative_geometry", "production_states", "real_cell_geometry",
        ],
        "representative_geometry_power": power,
        "production_state_ages": ages,
        "age_term_operational_impact": impact,
        "alpha_source": "EV_SE_DRIFT_V3_EVIDENCE.json (point estimates unchanged in v4)",
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print("WROTE", OUT)
    print(f"  max {impact['max_percent_change']}%  median {impact['median_percent_change']}%  "
          f"zero in {impact['cells_with_zero_change']}/{impact['cells_total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
