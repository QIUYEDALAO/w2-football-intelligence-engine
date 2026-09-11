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


def _age_seconds(capture_at: Any, evaluated_at: Any) -> float | None:
    from datetime import datetime

    if not capture_at or not evaluated_at:
        return None
    parse = lambda v: datetime.fromisoformat(str(v).replace("Z", "+00:00"))  # noqa: E731
    return round((parse(evaluated_at) - parse(capture_at)).total_seconds(), 3)


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


NOT_RECONSTRUCTIBLE = "NOT_RECONSTRUCTIBLE"


BUNDLE_NAME = "OFFICIAL_148_SOURCE_BUNDLE.jsonl"
BUNDLE_SCHEMA = "w2.official_candidate_source_bundle.v1"
# Exactly the fields build_rows consumes -- nothing else is copied out of the
# scoped production export, so the committed bundle carries no credentials, no
# connection strings, no team or provider payloads, and no raw provider bodies.
BUNDLE_RECOMMENDATION_FIELDS = (
    "evaluation_id", "fixture_id", "kickoff_utc", "market", "selection",
    "exact_line", "decimal_odds", "evaluated_at", "confirmed_checkpoint",
    "settlement", "profit_units", "score",
)
BUNDLE_EVALUATION_FIELDS = (
    "evaluation_slot_id", "scheduled_checkpoint_at", "original_state",
    "official_funnel_eligible", "first_failed_gate", "bookmaker_count",
    "capture_at", "model_forecast_capture_identity_hash", "quote_identity_hash",
    "opportunity_identity_hash", "attempt_identity_hash", "model_input_hash",
    "lineup_input_hash",
)
BUNDLE_PAYLOAD_FIELDS = (
    "opportunity_state", "blockers", "model_settlement_distribution",
    "one_x_two_probabilities", "current_ev", "current_ev_minus_se",
    "current_delta", "current_cashflow_price_edge", "calibration_status",
)


def build_bundle(recommendations: list[dict], evaluations: list[dict],
                 result_times: dict[str, str],
                 policy_versions: dict[str, str]) -> list[dict]:
    """Project the scoped export down to the committed, self-contained bundle.

    Run once against the restricted raw export; after that the official replay
    reads only the bundle, so acceptance never needs a file outside Git.
    """
    by_id = {str(row["evaluation_id"]): row for row in evaluations}
    bundle: list[dict] = []
    for rec in recommendations:
        if rec.get("settlement") not in SETTLED:
            continue
        evaluation_id = str(rec["evaluation_id"])
        evaluation = by_id.get(evaluation_id)
        if evaluation is None:
            raise ValueError(f"EVALUATION_NOT_FOUND:{evaluation_id}")
        payload = evaluation.get("payload") or {}
        bundle.append({
            "schema_version": BUNDLE_SCHEMA,
            **{key: rec.get(key) for key in BUNDLE_RECOMMENDATION_FIELDS},
            "result_available_at": result_times.get(str(rec["fixture_id"])),
            "evaluation_policy_version": policy_versions.get(evaluation_id),
            "evaluation": {key: evaluation.get(key) for key in BUNDLE_EVALUATION_FIELDS},
            "payload": {key: payload.get(key) for key in BUNDLE_PAYLOAD_FIELDS},
        })
    bundle.sort(key=lambda row: (str(row["kickoff_utc"]), str(row["evaluation_id"])))
    return bundle


def read_bundle(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        if row.get("schema_version") != BUNDLE_SCHEMA:
            raise ValueError(f"BUNDLE_SCHEMA_CONFLICT:{row.get('schema_version')}")
    return rows


def rows_from_bundle(bundle: list[dict]) -> list[dict]:
    """Adapt the bundle back into the four arguments build_rows already takes."""
    recommendations = [
        {key: row.get(key) for key in BUNDLE_RECOMMENDATION_FIELDS} for row in bundle
    ]
    evaluations = [
        {"evaluation_id": row["evaluation_id"], "payload": row.get("payload") or {},
         **(row.get("evaluation") or {})}
        for row in bundle
    ]
    result_times = {
        str(row["fixture_id"]): row.get("result_available_at") for row in bundle
    }
    policy_versions = {
        str(row["evaluation_id"]): row.get("evaluation_policy_version") for row in bundle
    }
    return build_rows(recommendations, evaluations, result_times, policy_versions)


def build_rows(recommendations: list[dict], evaluations: list[dict],
               result_times: dict[str, str], policy_versions: dict[str, str]) -> list[dict]:
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
            "factor_direction": NOT_RECONSTRUCTIBLE,
            "ev_direction": rec.get("selection"),
            "factor_veto_code": NOT_RECONSTRUCTIBLE,
            "factor_participants": NOT_RECONSTRUCTIBLE,
            "factor_weights": NOT_RECONSTRUCTIBLE,
            "factor_absent_reasons": NOT_RECONSTRUCTIBLE,
            "factor_verdict_identity": NOT_RECONSTRUCTIBLE,
            "factor_not_reconstructible_reason": (
                "No dynamic_prematch_evaluations payload in production contains any factor "
                "field, and analysis cards are a read-time projection with no table, so the "
                "verdict at this frozen instant cannot be recovered. Rebuilding it from a "
                "current card would be back-filling history."),
            # R6: the manifest must be self-contained.
            "result_available_at": result_times.get(str(rec["fixture_id"])),
            "evaluation_policy_version": policy_versions.get(str(rec["evaluation_id"])),
            "cashflow_edge_provenance": (
                "PERSISTED_IN_FROZEN_PAYLOAD"
                if payload.get("current_cashflow_price_edge") is not None
                else "NOT_ESTIMABLE_MISSING_CASHFLOW_EDGE"),
            "cashflow_edge_missing_reason": (
                None if payload.get("current_cashflow_price_edge") is not None
                else "EVALUATION_POLICY_V1_PREDATES_FIELD"),
            "lineup_status": (
                "LINEUP_INPUT_HASH_PRESENT" if evaluation.get("lineup_input_hash")
                else "NO_LINEUP_INPUT_HASH"),
            "lineup_starters_mapped": NOT_RECONSTRUCTIBLE,
            "lineup_valued_starters": NOT_RECONSTRUCTIBLE,
            "lineup_numeric_contribution": NOT_RECONSTRUCTIBLE,
            "lineup_not_reconstructible_reason": (
                "Lineup counts and numeric contribution live on the analysis card, which is "
                "not persisted; only lineup_input_hash survives on the evaluation."),
            "model_capture_at": evaluation.get("capture_at"),
            "model_age_seconds": _age_seconds(
                evaluation.get("capture_at"), rec.get("evaluated_at")),
            "lead_bucket": rec.get("confirmed_checkpoint"),
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
        "cashflow_edge_provenance_counts": {
            provenance: sum(1 for r in rows if r["cashflow_edge_provenance"] == provenance)
            for provenance in sorted({r["cashflow_edge_provenance"] for r in rows})},
        "evaluation_policy_versions": {
            version: sum(1 for r in rows if r["evaluation_policy_version"] == version)
            for version in sorted({str(r["evaluation_policy_version"]) for r in rows})},
        "result_available_at_present": sum(1 for r in rows if r["result_available_at"]),
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
    # Provenance only. The committed bundle is the input the official replay
    # uses; --raw rebuilds it from the restricted export and is not needed to
    # reproduce the manifest.
    parser.add_argument("--raw", type=Path, default=None)
    args = parser.parse_args()
    pkg = args.package
    bundle_path = pkg / BUNDLE_NAME
    if args.raw is not None:
        raw = args.raw
        bundle = build_bundle(
            load(raw / "_raw_official_recommendations.json"),
            load(raw / "_scoped_evaluations_148.json"),
            {r["fixture_id"]: r["result_available_at"]
             for r in load(raw / "_result_times.json")},
            {r["evaluation_id"]: r["evaluation_policy_version"]
             for r in load(raw / "_policy_versions.json")},
        )
        with bundle_path.open("w", encoding="utf-8") as handle:
            for row in bundle:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":")) + "\n")
    rows = rows_from_bundle(read_bundle(bundle_path))
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
