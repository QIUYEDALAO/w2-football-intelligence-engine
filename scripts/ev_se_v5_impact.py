#!/usr/bin/env python3
"""Operational impact of an age term, on production's real window.

Protocol v5 sections 2 and 3 (commit 4558f5ab).

v4 built its evaluation windows per season and reported a 10th-to-90th percentile
age span of 5.9 to 28.2 days, from which it concluded the age term was too small
for production to notice. Under production's cross-season window the span is 55 to
180 days and the term moves SE by up to about half. That conclusion is withdrawn,
and this script is the committed source for its replacement.

Every state comes from `ev_se_v5_window`, so the season-reset defect cannot recur
here silently -- `ev_se_v5_window.self_check` fails if it does.

Two populations are named and never mixed: `production_states` for the age
distribution and the impact, and `representative_geometry` for the synthetic power
design, which lives in the v4 impact artefact and is not recomputed.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))
import ev_se_v5_window as W

OUT = os.path.join(
    os.path.dirname(__file__), "..", "docs", "review_packages",
    "EV_SE_DRIFT_V5", "EV_SE_DRIFT_V5_IMPACT.json",
)
EVIDENCE_V4 = os.path.join(
    os.path.dirname(__file__), "..", "docs", "review_packages",
    "EV_SE_DRIFT_V4", "EV_SE_DRIFT_V4_EVIDENCE.json",
)


def _quantile(values: list[float], p: float) -> float:
    return float(sorted(values)[int(p * len(values))])


def distributions() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for component in ("attack", "defence"):
        for cell, states in sorted(W.observed_states(component).items()):
            ages = [s["mean_age_days"] for s in states]
            se0 = [s["se0_squared"] for s in states]
            out[cell] = {
                "states": len(states),
                "age_p10_days": round(_quantile(ages, 0.10), 3),
                "age_p50_days": round(_quantile(ages, 0.50), 3),
                "age_p90_days": round(_quantile(ages, 0.90), 3),
                "age_p10_to_p90_span_days": round(
                    _quantile(ages, 0.90) - _quantile(ages, 0.10), 3
                ),
                "se0_squared_p10": _quantile(se0, 0.10),
                "se0_squared_p50": _quantile(se0, 0.50),
                "se0_squared_p90": _quantile(se0, 0.90),
            }
    return out


def impact(cells: dict[str, Any]) -> dict[str, Any]:
    with open(EVIDENCE_V4, encoding="utf-8") as fh:
        evidence = json.load(fh)
    out: dict[str, Any] = {}
    for cell, stats in cells.items():
        entry = evidence["alpha_cells"][cell]["mle"]
        alpha = entry["sigma2_alpha_abs"]
        ci = entry["profile_ci_95"]["interval"]
        base = stats["se0_squared_p50"]

        def ratio(rate: float, base: float = base, stats: dict[str, Any] = stats) -> float:
            lo = (base + rate * float(stats["age_p10_days"])) ** 0.5
            hi = (base + rate * float(stats["age_p90_days"])) ** 0.5
            return float(hi / lo)

        row: dict[str, Any] = {
            "alpha_abs": alpha,
            "alpha_at_boundary": alpha == 0.0,
            "se_percent_change_at_point_estimate": round((ratio(alpha) - 1.0) * 100.0, 4),
        }
        if ci[0] is not None and ci[1] is not None:
            row["se_percent_change_at_ci_low"] = round((ratio(ci[0]) - 1.0) * 100.0, 4)
            row["se_percent_change_at_ci_high"] = round((ratio(ci[1]) - 1.0) * 100.0, 4)
        out[cell] = row
    changes = sorted(v["se_percent_change_at_point_estimate"] for v in out.values())
    return {
        "cells": out,
        "max_percent_change": changes[-1],
        "median_percent_change": changes[len(changes) // 2],
        "cells_with_zero_change": sum(1 for c in changes if c == 0.0),
        "cells_total": len(changes),
        "reading": (
            "this is the size of the correction an age term would apply across the "
            "ages production actually sees. It is not evidence that the correction is "
            "right: the same alpha carries a profile interval spanning roughly a "
            "factor of five, and windows this long cross season breaks, which is the "
            "regime the boundary jump term found the random walk over-predicting"
        ),
    }


def main() -> int:
    guard = W.self_check()
    if guard["result"] != "PASS":
        print(json.dumps(guard, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    cells = distributions()
    payload: dict[str, Any] = {
        "schema_version": "w2.ev_se.drift_v5.impact.v1",
        "protocol_commit": "4558f5ab",
        "population": "production_states",
        "window_semantics": (
            "latest 20 xG rows by kickoff across seasons, as "
            "team_xg_matches_for_teams orders them; built by ev_se_v5_window"
        ),
        "window_self_check": guard,
        "supersedes": {
            "file": "EV_SE_DRIFT_V4_IMPACT.json",
            "defect": (
                "v4 grouped evaluation windows by (league, team, season), so no window "
                "spanned a season break and the age span came out four to fifteen "
                "times too narrow"
            ),
        },
        "state_distributions": cells,
        "age_term_operational_impact": impact(cells),
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    summary: dict[str, Any] = payload["age_term_operational_impact"]
    print(json.dumps({
        "wrote": OUT,
        "max_percent_change": summary["max_percent_change"],
        "median_percent_change": summary["median_percent_change"],
        "cells_with_zero_change": summary["cells_with_zero_change"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
