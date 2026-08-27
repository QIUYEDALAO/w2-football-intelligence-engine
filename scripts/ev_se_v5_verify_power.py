#!/usr/bin/env python3
"""Re-run one power cell, compare it field by field, and record what was compared.

Protocol v5 section 6 (commit 4558f5ab).

v4's freeze tool wrote `verified: true` because a `--verified-cell` flag had been
passed. Nothing was compared and no observed values were stored, so a reviewer had
to take the claim on trust. v4 also called the match "bit for bit" while the record
carried `seconds`, which is wall clock and cannot match across runs.

This tool recomputes a cell under the canonical power code, compares the two fields
that are deterministic, writes **both sides' observed values** into the artefact
next to the verdict, and moves the timing field somewhere it cannot be mistaken for
evidence. `verified: true` here is only ever written after a comparison ran.

    python3 scripts/ev_se_v5_verify_power.py --source <v4_power.json> --cell "<cell>"
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))
import ev_se_mle as M
import ev_se_v4_power as P

OUT = os.path.join(
    os.path.dirname(__file__), "..", "docs", "review_packages",
    "EV_SE_DRIFT_V5", "EV_SE_DRIFT_V5_POWER.json",
)
COMPARED_FIELDS = ("mle_rejection_rate", "variogram_rejection_rate")
EXCLUDED_FIELDS = ("seconds",)


def recompute(cell: str) -> dict[str, dict[str, float]]:
    """Run the canonical power computation for one cell."""
    series = P.cell_series()[cell]
    times = [[t for t, _ in s] for s in series]
    _sigma2, tau2, _ll = M.fit_full(series)
    grid: dict[str, dict[str, float]] = {}
    for sigma2 in P.SIGMA2_GRID:
        rng = random.Random(P.SEED)  # noqa: S311 - statistical replication, not crypto
        mle_hits = var_hits = 0
        for _ in range(P.REPLICATIONS):
            replicate = P.draw(rng, times, sigma2, tau2)
            _s, _t, ll_full = M.fit_full(replicate)
            _tr, ll_null = M.fit_restricted(replicate)
            if M.lrt_pvalue(ll_full, ll_null) < 0.05:
                mle_hits += 1
            if P.variogram_detects(replicate):
                var_hits += 1
        grid[f"{sigma2:.1e}"] = {
            "mle_rejection_rate": mle_hits / P.REPLICATIONS,
            "variogram_rejection_rate": var_hits / P.REPLICATIONS,
        }
        print(f"  {sigma2:.1e} recomputed", flush=True)
    return grid


def main() -> int:
    source_path = cell = None
    for index, argument in enumerate(sys.argv):
        if argument == "--source" and index + 1 < len(sys.argv):
            source_path = sys.argv[index + 1]
        if argument == "--cell" and index + 1 < len(sys.argv):
            cell = sys.argv[index + 1]
    if source_path is None or cell is None:
        print("usage: --source <power.json> --cell <cell>", file=sys.stderr)
        return 2

    with open(source_path, "rb") as fh:
        source_bytes = fh.read()
    source: dict[str, Any] = json.loads(source_bytes)
    stored = source["cells"][cell]["grid"]

    recomputed = recompute(cell)
    comparisons: list[dict[str, Any]] = []
    mismatches = 0
    for key in sorted(stored):
        for field in COMPARED_FIELDS:
            left, right = stored[key][field], recomputed[key][field]
            equal = left == right
            mismatches += 0 if equal else 1
            comparisons.append(
                {"grid_point": key, "field": field, "artefact_value": left,
                 "recomputed_value": right, "equal": equal}
            )

    cells: dict[str, Any] = {}
    for name, entry in source["cells"].items():
        grid = {}
        for key, point in entry["grid"].items():
            grid[key] = {f: point[f] for f in COMPARED_FIELDS}
            grid[key]["timing_not_compared"] = {f: point[f] for f in EXCLUDED_FIELDS}
        cells[name] = {**{k: v for k, v in entry.items() if k != "grid"}, "grid": grid}

    payload = {
        "schema_version": "w2.ev_se.drift_v5.power.v1",
        "protocol_commit": "4558f5ab",
        "population": "real_cell_geometry",
        "replications": source["replications"],
        "seed": source["seed"],
        "sigma2_grid": source["sigma2_grid"],
        "provenance": {
            "numbers_from": os.path.basename(source_path),
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "produced_by": "scripts/ev_se_v3_power.py",
            "canonical_script": "scripts/ev_se_v4_power.py",
            "note": (
                "the power computation is unchanged across v3, v4 and v5; only the "
                "output path and the provenance stamp ever differed"
            ),
        },
        "equivalence_check": {
            "tool": "scripts/ev_se_v5_verify_power.py",
            "cell": cell,
            "compared_fields": list(COMPARED_FIELDS),
            "excluded_fields": list(EXCLUDED_FIELDS),
            "why_excluded": "wall-clock timing cannot reproduce and is not evidence",
            "comparisons": comparisons,
            "mismatches": mismatches,
            "verified": mismatches == 0,
            "supersedes": (
                "EV_SE_DRIFT_V4_POWER.json recorded verified:true because a flag was "
                "passed; no comparison had been performed"
            ),
        },
        "cells": cells,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "wrote": OUT, "cell": cell, "comparisons": len(comparisons),
        "mismatches": mismatches, "verified": mismatches == 0,
    }))
    return 0 if mismatches == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
