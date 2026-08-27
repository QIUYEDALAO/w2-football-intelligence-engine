#!/usr/bin/env python3
"""What would more seasons buy? Measured, not argued.

Protocol v6 section 6 (commit b74766f9).

v5 said "more seasons add cells, not resolution". That was wrong. The 26 cells are
fixed by league and component; what more seasons add is team-season series *inside*
each cell, and the likelihood accumulates across series, so they do add estimation
information.

The useful question is how much. This repeats the power study at the drift rate that
moves `SE` about ten percent over sixty days -- `sigma^2 = 1e-4` at the measured
median `SE0^2` -- with each cell's series count scaled by 1, 2, 4 and 8, drawing the
extra series from the same real timestamp geometry. The report then says what
multiple of today's data reaches eighty percent power, or that none in range does.
"""
from __future__ import annotations

import json
import os
import random
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))
import ev_se_mle as M
import ev_se_v4_power as P

SEED = 20260826
REPLICATIONS = 500
SIGMA2 = 1e-4
SCALES = (1, 2, 4, 8)
TARGET_POWER = 0.80
OUT = os.path.join(
    os.path.dirname(__file__), "..", "docs", "review_packages",
    "EV_SE_DRIFT_V6", "EV_SE_DRIFT_V6_SCALING.json",
)


def main() -> int:
    cells = P.cell_series()
    report: dict[str, Any] = {}
    for cell in sorted(cells):
        real = cells[cell]
        times = [[t for t, _ in s] for s in real]
        _sigma2, tau2, _ll = M.fit_full(real)
        curve: dict[str, float] = {}
        for scale in SCALES:
            geometry = times * scale
            rng = random.Random(SEED)  # noqa: S311 - statistical replication, not crypto
            hits = 0
            for _ in range(REPLICATIONS):
                replicate = P.draw(rng, geometry, SIGMA2, tau2)
                _s, _t, ll_full = M.fit_full(replicate)
                _tr, ll_null = M.fit_restricted(replicate)
                if M.lrt_pvalue(ll_full, ll_null) < 0.05:
                    hits += 1
            curve[f"x{scale}"] = hits / REPLICATIONS
            print(f"{cell:32s} x{scale} power={hits / REPLICATIONS:.3f}", flush=True)
        reached = [s for s in SCALES if curve[f"x{s}"] >= TARGET_POWER]
        report[cell] = {
            "series_today": len(real),
            "tau2_used": tau2,
            "power_by_scale": curve,
            "smallest_scale_reaching_80pc": reached[0] if reached else None,
        }
    reached_any = [k for k, v in report.items() if v["smallest_scale_reaching_80pc"]]
    payload = {
        "schema_version": "w2.ev_se.drift_v6.scaling.v1",
        "protocol_commit": "b74766f9",
        "population": "real_cell_geometry, series count replicated",
        "sigma2": SIGMA2,
        "sigma2_meaning": "the drift rate that moves SE about 10% over 60 days",
        "replications": REPLICATIONS,
        "seed": SEED,
        "scales": list(SCALES),
        "target_power": TARGET_POWER,
        "cells_reaching_80pc_within_range": reached_any,
        "cells": report,
        "reading": (
            "scaling the series count is the shape more seasons take: the cells are "
            "fixed, the series inside them are not. This measures what that buys and "
            "does not model anything else more data would change"
        ),
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"wrote": OUT, "cells_reaching_80pc": len(reached_any)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
