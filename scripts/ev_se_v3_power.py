#!/usr/bin/env python3
"""Per-cell power and size study, protocol v3 section 4 (commit 603a9753).

Synthetic series are drawn on the *real* timestamp geometry of each cell, with
that cell's own fitted tau^2 and an injected sigma^2 from the frozen grid. Both
estimators see identical replicates, so the comparison is paired.

sigma^2 = 0 is on the grid on purpose: it measures the size of each test. Power
quoted without a size check is not evidence.
"""
from __future__ import annotations

import json
import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import ev_se_mle as M
import ev_se_variogram as V
from _load import load

SIGMA2_GRID = (0.0, 1e-5, 3e-5, 1e-4, 3e-4, 1e-3)
REPLICATIONS = 500
SEED = 20260826
OUT = os.path.join(
    os.path.dirname(__file__), "..", "docs", "review_packages",
    "EV_SE_DRIFT_V3", "EV_SE_DRIFT_V3_POWER.json",
)


def cell_series() -> dict[str, list[list[tuple[float, float]]]]:
    """cell -> the real per-series observations. Loaded once; the corpus is large."""
    cells: dict[str, list[list[tuple[float, float]]]] = {}
    for comp in ("attack", "defence"):
        for (league, _team, _season), series in load(comp).items():
            if len(series) < 3:
                continue
            cells.setdefault(f"{league}|{comp}", []).append(sorted(series))
    return cells


def draw(rng: random.Random, times: list[list[float]], sigma2: float, tau2: float):
    out = []
    for ts in times:
        level = 0.0
        prev = ts[0]
        series = []
        for t in ts:
            if t > prev:
                level += rng.gauss(0.0, math.sqrt(sigma2 * (t - prev)))
            series.append((t, level + rng.gauss(0.0, math.sqrt(tau2))))
            prev = t
        out.append(series)
    return out


def variogram_detects(replicate) -> bool:
    rows: list[tuple[str, float, float]] = []
    for i, series in enumerate(replicate):
        team = str(i)
        for a in range(len(series)):
            ta, ya = series[a]
            for b in range(a + 1, len(series)):
                tb, yb = series[b]
                rows.append((team, tb - ta, (yb - ya) ** 2))
    lo, _ = V.bootstrap(V.team_stats(rows))
    return lo is not None and lo > 0.0


def main() -> int:
    cells = cell_series()
    report: dict[str, object] = {}
    for cell in sorted(cells):
        real = cells[cell]
        times = [[t for t, _ in s] for s in real]
        # tau^2 comes from this cell's own fit on the real data
        _sigma2_hat, tau2_hat, _ll = M.fit_full(real)
        grid: dict[str, object] = {}
        for sigma2 in SIGMA2_GRID:
            rng = random.Random(SEED)  # noqa: S311 - statistical replication, not crypto
            mle_hits = var_hits = 0
            started = time.time()
            for _ in range(REPLICATIONS):
                replicate = draw(rng, times, sigma2, tau2_hat)
                _s, _t, ll_full = M.fit_full(replicate)
                _tr, ll_null = M.fit_restricted(replicate)
                if M.lrt_pvalue(ll_full, ll_null) < 0.05:
                    mle_hits += 1
                if variogram_detects(replicate):
                    var_hits += 1
            grid[f"{sigma2:.1e}"] = {
                "mle_rejection_rate": mle_hits / REPLICATIONS,
                "variogram_rejection_rate": var_hits / REPLICATIONS,
                "seconds": round(time.time() - started, 1),
            }
            print(
                f"{cell:32s} sigma2={sigma2:.1e} mle={mle_hits / REPLICATIONS:.3f} "
                f"vario={var_hits / REPLICATIONS:.3f}",
                flush=True,
            )
        size = grid["0.0e+00"]["mle_rejection_rate"]  # type: ignore[index]
        report[cell] = {
            "series": len(times),
            "tau2_used": tau2_hat,
            "grid": grid,
            "mle_size_at_null": size,
            "status": "TEST_MISCALIBRATED" if size > 0.08 else "CALIBRATED",
        }
    payload = {
        "schema_version": "w2.ev_se.drift_v3.power.v1",
        "protocol_commit": "603a9753",
        "replications": REPLICATIONS,
        "seed": SEED,
        "sigma2_grid": list(SIGMA2_GRID),
        "cells": report,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print("WROTE", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
