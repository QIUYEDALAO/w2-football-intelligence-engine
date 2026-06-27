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
from w2.backtest.s2_readiness import S2ReadinessInputs, build_s2_readiness_report  # noqa: E402


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
    parser.add_argument("--features-jsonl", type=Path, help="As-of feature artifact JSON/JSONL.")
    parser.add_argument("--labels-jsonl", type=Path, help="Settled label artifact JSON/JSONL.")
    parser.add_argument(
        "--data-source",
        default="UNSPECIFIED",
        help="Human-readable report source.",
    )
    parser.add_argument(
        "--authoritative",
        action="store_true",
        help="Mark source as authoritative only if it is not demo/synthetic.",
    )
    parser.add_argument("--output-report", type=Path, help="Write report JSON to this path.")
    args = parser.parse_args()
    if args.dry_run and not (args.features_jsonl or args.labels_jsonl):
        payload = dry_run_payload()
    else:
        payload = build_s2_readiness_report(
            S2ReadinessInputs(
                features_path=args.features_jsonl,
                labels_path=args.labels_jsonl,
                data_source=args.data_source,
                requested_authoritative=args.authoritative,
            )
        )
    encoded = json.dumps(payload, sort_keys=True)
    if args.output_report is not None:
        args.output_report.parent.mkdir(parents=True, exist_ok=True)
        args.output_report.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
