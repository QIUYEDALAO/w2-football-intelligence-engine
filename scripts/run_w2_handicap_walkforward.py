from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from w2.backtest.handicap_walkforward import (  # noqa: E402
    WalkForwardInputs,
    build_handicap_walkforward_report,
    dry_run_report,
    load_rows_from_read_model,
    load_rows_from_source_root,
)
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
    parser.add_argument("--mode", choices=["real", "demo", "dry-run"], default=None)
    parser.add_argument("--from", dest="date_from", help="Start date YYYY-MM-DD.")
    parser.add_argument("--to", dest="date_to", help="End date YYYY-MM-DD.")
    parser.add_argument("--min-samples", type=int, default=S2_MIN_COVERED_SETTLED_SAMPLE)
    parser.add_argument("--json", action="store_true", help="Emit compact JSON.")
    parser.add_argument("--include-rows", action="store_true", help="Include evaluated rows.")
    parser.add_argument(
        "--source-root",
        type=Path,
        help="Optional source artifact root or JSON file.",
    )
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
    if args.dry_run and not args.json and not (args.features_jsonl or args.labels_jsonl):
        payload = dry_run_payload()
        encoded = json.dumps(payload, sort_keys=True)
        if args.output_report is not None:
            args.output_report.parent.mkdir(parents=True, exist_ok=True)
            args.output_report.write_text(encoded + "\n", encoding="utf-8")
        print(encoded)
        return 0
    mode = "dry-run" if args.dry_run else (args.mode or "dry-run")
    if mode in {"real", "demo", "dry-run"} and not (args.features_jsonl or args.labels_jsonl):
        if mode == "dry-run":
            payload = dry_run_report(include_rows=args.include_rows)
        else:
            rows = load_rows_from_source_root(args.source_root)
            if mode == "real" and not rows and args.source_root is None:
                rows = load_rows_from_read_model()
            payload = build_handicap_walkforward_report(
                WalkForwardInputs(
                    mode=mode,
                    rows=rows,
                    data_source=args.data_source
                    if args.data_source != "UNSPECIFIED"
                    else _data_source_for_mode(mode, args.source_root),
                    date_from=_date_or_none(args.date_from),
                    date_to=_date_or_none(args.date_to),
                    min_samples=args.min_samples,
                    include_rows=args.include_rows,
                )
            )
    elif args.dry_run and not (args.features_jsonl or args.labels_jsonl):
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


def _date_or_none(value: str | None) -> Any:
    if value is None:
        return None
    from datetime import date

    return date.fromisoformat(value)


def _data_source_for_mode(mode: str, source_root: Path | None) -> str:
    if source_root is not None:
        return source_root.as_posix()
    if mode == "real":
        return "read-model-db"
    if mode == "demo":
        return "demo"
    return "DRY_RUN_NO_ASOF_ARTIFACT"


if __name__ == "__main__":
    raise SystemExit(main())
