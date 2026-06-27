from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from w2.backtest.s2_gate import (  # noqa: E402
    S2_MIN_COVERED_SETTLED_SAMPLE,
    S2GateEvidence,
    s2_walkforward_shadow_status,
)


def dry_run_payload() -> dict[str, Any]:
    gate = s2_walkforward_shadow_status(
        S2GateEvidence(
            covered_settled_sample=0,
            noise_separated_advantage=False,
            time_split_passed=False,
            holdout_replicated=False,
            forward_shadow_passed=False,
        )
    )
    return {
        "samples": 0,
        "n_min": S2_MIN_COVERED_SETTLED_SAMPLE,
        "beats_market": False,
        "reason": "INSUFFICIENT_VALIDATED_SAMPLES",
        "status": "ANALYSIS_ONLY",
        "report_type": "S2_VALIDATION_READINESS_DRY_RUN",
        "settlement_policy": {
            "market_snapshot": "AS_OF_LOCKED_MARKET_SNAPSHOT_REQUIRED",
            "devig_method": "REQUIRED_FOR_MARKET_BASELINE",
            "asian_handicap_outcomes": [
                "WIN",
                "HALF_WIN",
                "PUSH",
                "HALF_LOSS",
                "LOSS",
                "VOID",
            ],
            "push_counts_as_win": False,
            "void_included_in_sample": False,
        },
        "gate": gate,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run W2 handicap walk-forward audit.")
    parser.add_argument("--dry-run", action="store_true", help="Emit the Wave-1 skeleton payload.")
    args = parser.parse_args()
    if not args.dry_run:
        parser.error("only --dry-run is supported in Wave-1")
    print(json.dumps(dry_run_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
