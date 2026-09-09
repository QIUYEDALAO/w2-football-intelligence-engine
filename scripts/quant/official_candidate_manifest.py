"""Task A: freeze the 148 settled official candidates into a manifest.

Read-only. Joins the public official_recommendations projection to the
dynamic_prematch_evaluations rows already exported for exactly those 148
evaluation ids, and independently recomputes the headline totals without
importing any production serializer.
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

SETTLED = ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")
# The dynamic evaluation payload has never carried a factor verdict: a
# whole-table scan of dynamic_prematch_evaluations for the substring "factor"
# returned 0 rows, and analysis cards are a read-time projection with no table.
FACTOR_DISPOSITION = "UNKNOWN_NOT_RECONSTRUCTIBLE"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_rows(recommendations: list[dict], evaluations: list[dict]) -> list[dict]:
    by_id = {str(row["evaluation_id"]): row for row in evaluations}
    out: list[dict] = []
    for rec in recommendations:
        if rec.get("settlement") not in SETTLED:
            continue
        evaluation = by_id.get(str(rec["evaluation_id"]))
        if evaluation is None:
            raise ValueError(f"EVALUATION_NOT_FOUND:{rec['evaluation_id']}")
        payload = evaluation.get("payload") or {}
        out.append({
            "evaluation_id": str(rec["evaluation_id"]),
            "fixture_id": str(rec["fixture_id"]),
            "kickoff_utc": rec.get("kickoff_utc"),
            "market": rec.get("market"),
            "selection": rec.get("selection"),
            "exact_line": rec.get("exact_line"),
            "decimal_odds": rec.get("decimal_odds"),
            "evaluated_at": rec.get("evaluated_at"),
            "confirmed_checkpoint": rec.get("confirmed_checkpoint"),
            "evaluation_slot_id": evaluation.get("evaluation_slot_id"),
            "scheduled_checkpoint_at": evaluation.get("scheduled_checkpoint_at"),
            "settlement": rec.get("settlement"),
            "profit_units": rec.get("profit_units"),
            "score": rec.get("score"),
            "original_state": evaluation.get("original_state"),
            "opportunity_state": payload.get("opportunity_state"),
            "official_funnel_eligible": evaluation.get("official_funnel_eligible"),
            "first_failed_gate": evaluation.get("first_failed_gate"),
            "blockers": payload.get("blockers"),
            "bookmaker_count": evaluation.get("bookmaker_count"),
            "model_settlement_distribution": payload.get("model_settlement_distribution"),
            "one_x_two_probabilities": payload.get("one_x_two_probabilities"),
            "current_ev": payload.get("current_ev"),
            "current_ev_minus_se": payload.get("current_ev_minus_se"),
            "current_delta": payload.get("current_delta"),
            "current_cashflow_price_edge": payload.get("current_cashflow_price_edge"),
            "calibration_status": payload.get("calibration_status"),
            "capture_at": evaluation.get("capture_at"),
            "model_forecast_capture_identity_hash": evaluation.get(
                "model_forecast_capture_identity_hash"),
            "quote_identity_hash": evaluation.get("quote_identity_hash"),
            "opportunity_identity_hash": evaluation.get("opportunity_identity_hash"),
            "attempt_identity_hash": evaluation.get("attempt_identity_hash"),
            "model_input_hash": evaluation.get("model_input_hash"),
            "lineup_input_hash": evaluation.get("lineup_input_hash"),
            # Never reconstructed from a current analysis card.
            "factor_disposition": FACTOR_DISPOSITION,
            "factor_direction": None,
            "ev_direction": rec.get("selection"),
            "factor_veto_code": None,
        })
    out.sort(key=lambda row: (str(row["kickoff_utc"]), row["evaluation_id"]))
    return out


def recompute(rows: list[dict]) -> dict:
    """Independent recomputation. No production serializer is imported."""
    total = sum(Decimal(str(row["profit_units"] or 0)) for row in rows)
    last10 = rows[-10:]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["settlement"]] = counts.get(row["settlement"], 0) + 1
    last10_counts: dict[str, int] = {}
    for row in last10:
        last10_counts[row["settlement"]] = last10_counts.get(row["settlement"], 0) + 1
    return {
        "settled_rows": len(rows),
        "distinct_fixtures": len({row["fixture_id"] for row in rows}),
        "profit_units_total": str(total),
        "settlement_counts": dict(sorted(counts.items())),
        "last10_settlement_counts": dict(sorted(last10_counts.items())),
        "last10_profit_units": str(
            sum(Decimal(str(row["profit_units"] or 0)) for row in last10)),
        "market_counts": {
            market: sum(1 for row in rows if row["market"] == market)
            for market in sorted({row["market"] for row in rows})},
        "factor_identity_coverage": {
            "reconstructible": sum(
                1 for row in rows if row["factor_disposition"] != FACTOR_DISPOSITION),
            "unknown_not_reconstructible": sum(
                1 for row in rows if row["factor_disposition"] == FACTOR_DISPOSITION),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()
    pkg = args.package
    rows = build_rows(
        load(pkg / "_raw_official_recommendations.json"),
        load(pkg / "_scoped_evaluations_148.json"),
    )
    with (pkg / "OFFICIAL_148_MANIFEST.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")) + "\n")
    summary = recompute(rows)
    (pkg / "OFFICIAL_148_RECOMPUTATION.json").write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
