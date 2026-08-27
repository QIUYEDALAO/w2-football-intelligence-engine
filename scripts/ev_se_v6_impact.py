#!/usr/bin/env python3
"""Age distribution, SE0^2 and operational impact on the authoritative epoch set.

Protocol v6 sections 3 and 7 (commit b74766f9).

Recomputed because v5 drew epochs from the xG-carrying series. Two conditions were
imposed that production does not impose, and the second is larger than the first:

  *   872 epochs required the target fixture to produce xG afterwards;
  * 5,082 epochs required a full 20-row window, because v5 sliced `series[i-20:i]`
    out of the xG series. `_xg_standard_error` fails closed below three rows, not
    below twenty.

Together those are exactly the 8,578 v5 reported against the 14,290 production
actually reaches.

Alpha estimates, the per-cell power study and the behavioural results are unchanged
and are not re-derived here.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))
import ev_se_v6_epochs as E

OUT = os.path.join(
    os.path.dirname(__file__), "..", "docs", "review_packages",
    "EV_SE_DRIFT_V6", "EV_SE_DRIFT_V6_IMPACT.json",
)
EVIDENCE_V5 = os.path.join(
    os.path.dirname(__file__), "..", "docs", "review_packages",
    "EV_SE_DRIFT_V5", "EV_SE_DRIFT_V5_EVIDENCE.json",
)


def _q(values: list[float], p: float) -> float:
    return float(sorted(values)[int(p * len(values))])


def distributions() -> tuple[dict[str, Any], dict[str, Any]]:
    cells: dict[str, Any] = {}
    ledgers: dict[str, Any] = {}
    for component in ("attack", "defence"):
        produced = E.analysis_epochs(component)
        ledgers[component] = produced["ledger"]
        for cell, states in sorted(produced["cells"].items()):
            ages = [s["mean_age_days"] for s in states]
            se0 = [s["se0_squared"] for s in states]
            counts = [s["observed"] for s in states]
            cells[cell] = {
                "epochs": len(states),
                "epochs_with_full_20_window": sum(1 for c in counts if c == 20),
                "epochs_with_target_xg": sum(1 for s in states if s["target_has_xg"]),
                "window_rows_p10": _q([float(c) for c in counts], 0.10),
                "window_rows_p50": _q([float(c) for c in counts], 0.50),
                "age_p10_days": round(_q(ages, 0.10), 3),
                "age_p50_days": round(_q(ages, 0.50), 3),
                "age_p90_days": round(_q(ages, 0.90), 3),
                "age_p10_to_p90_span_days": round(_q(ages, 0.90) - _q(ages, 0.10), 3),
                "se0_squared_p10": _q(se0, 0.10),
                "se0_squared_p50": _q(se0, 0.50),
                "se0_squared_p90": _q(se0, 0.90),
                "se0_squared_spread_p90_over_p10": round(
                    _q(se0, 0.90) / _q(se0, 0.10), 6
                ),
            }
    return cells, ledgers


def impact(cells: dict[str, Any]) -> dict[str, Any]:
    with open(EVIDENCE_V5, encoding="utf-8") as fh:
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
    non_boundary = [k for k, v in out.items() if not v["alpha_at_boundary"]]
    band_reaches_zero = [
        k for k in non_boundary if out[k].get("se_percent_change_at_ci_low", 0.0) == 0.0
    ]
    return {
        "cells": out,
        "max_percent_change": changes[-1],
        "median_percent_change": changes[len(changes) // 2],
        "cells_with_zero_change": sum(1 for c in changes if c == 0.0),
        "cells_total": len(changes),
        "non_boundary_cells": len(non_boundary),
        "non_boundary_cells_whose_band_reaches_zero": len(band_reaches_zero),
        "reading": (
            "the size of the correction an age term would apply across the ages "
            "production actually sees. Not evidence the correction is right: alpha's "
            "own profile interval spans roughly a factor of five, and the longest "
            "windows cross season breaks, which is where the boundary jump term "
            "found the random walk over-predicting"
        ),
    }


def main() -> int:
    guard = E.self_check()
    if guard["result"] != "PASS":
        print(json.dumps(guard, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    cells, ledgers = distributions()
    payload: dict[str, Any] = {
        "schema_version": "w2.ev_se.drift_v6.impact.v1",
        "protocol_commit": "b74766f9",
        "population": "production_evaluation_epochs",
        "population_definition": (
            "every (team, finished fixture) pair at that fixture's kickoff; window is "
            "the latest 20 xG rows with kickoff < as_of across seasons; admitted when "
            "at least 3 rows carry positive sample variance, as _xg_standard_error "
            "requires. Whether the target later produced xG is not an admission rule"
        ),
        "admission_ledger": ledgers,
        "epoch_guard": guard,
        "supersedes": {
            "file": "EV_SE_DRIFT_V5_IMPACT.json",
            "defects": [
                "epochs drawn from the xG-carrying series, so the target had to "
                "produce xG afterwards (872 epochs)",
                "windows sliced as series[i-20:i], so a full 20-row window was "
                "required where production fails closed below three (5,082 epochs)",
            ],
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
        "non_boundary_cells_whose_band_reaches_zero": (
            f"{summary['non_boundary_cells_whose_band_reaches_zero']}"
            f"/{summary['non_boundary_cells']}"
        ),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
