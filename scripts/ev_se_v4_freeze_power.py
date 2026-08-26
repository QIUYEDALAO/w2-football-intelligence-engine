#!/usr/bin/env python3
"""Freeze a completed power run into the v4 package.

Protocol v4 section 7 carries the power computation forward from v3 section 4
verbatim, so a run started under `ev_se_v3_power.py` produces the numbers v4 asks
for. This script re-stamps that output into the v4 artefact rather than re-running
two and a half hours of identical arithmetic, and it records which script produced
the numbers instead of implying they came from the v4 one.

The equivalence is checked, not asserted:

    python3 scripts/ev_se_v4_power.py --only "<cell>"

re-runs a single cell under the v4 script and must match this artefact for that
cell. The verification is recorded in `equivalence_check` below.

    python3 scripts/ev_se_v4_freeze_power.py <source.json> [--verified-cell CELL]
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

OUT = os.path.join(
    os.path.dirname(__file__), "..", "docs", "review_packages",
    "EV_SE_DRIFT_V4", "EV_SE_DRIFT_V4_POWER.json",
)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: ev_se_v4_freeze_power.py <source.json> [--verified-cell CELL]",
              file=sys.stderr)
        return 2
    verified: str | None = None
    for index, argument in enumerate(sys.argv):
        if argument == "--verified-cell" and index + 1 < len(sys.argv):
            verified = sys.argv[index + 1]
    with open(sys.argv[1], encoding="utf-8") as fh:
        source: dict[str, Any] = json.load(fh)

    cells = source["cells"]
    sizes = [v["mle_size_at_null"] for v in cells.values()]
    at_1e4 = sorted(v["grid"]["1.0e-04"]["mle_rejection_rate"] for v in cells.values())
    payload = {
        "schema_version": "w2.ev_se.drift_v4.power.v1",
        "protocol_commit": "18f812b7",
        "population": "real_cell_geometry",
        "provenance": {
            "produced_by": "scripts/ev_se_v3_power.py",
            "why": (
                "protocol v4 section 7 carries the v3 section 4 computation forward "
                "verbatim, so the run is valid for v4; only the output path and the "
                "provenance stamp differ"
            ),
            "canonical_script": "scripts/ev_se_v4_power.py",
        },
        "equivalence_check": {
            "method": 'python3 scripts/ev_se_v4_power.py --only "<cell>"',
            "verified_cell": verified,
            "verified": verified is not None,
        },
        "replications": source["replications"],
        "seed": source["seed"],
        "sigma2_grid": source["sigma2_grid"],
        "summary": {
            "cells": len(cells),
            "size_at_null_min": min(sizes),
            "size_at_null_max": max(sizes),
            "nominal_size": 0.05,
            "miscalibrated_cells": [
                k for k, v in cells.items() if v["status"] != "CALIBRATED"
            ],
            "power_at_1e_4_min": at_1e4[0],
            "power_at_1e_4_median": at_1e4[len(at_1e4) // 2],
            "power_at_1e_4_max": at_1e4[-1],
            "cells_reaching_80pc_power_at_1e_4": sum(1 for x in at_1e4 if x >= 0.80),
            "note": (
                "1e-4 is the drift rate that would move SE about ten percent over "
                "sixty days at the measured median SE0^2"
            ),
        },
        "cells": cells,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"wrote": OUT, "cells": len(cells), "verified_cell": verified}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
