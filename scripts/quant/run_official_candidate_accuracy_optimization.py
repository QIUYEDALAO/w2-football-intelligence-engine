"""Task 2: evaluate GLOBAL_ROLLING_CONFIDENCE_SHRINKAGE_V1 on the 148 candidates.

Offline. Reads only the frozen, hash-verified evidence package; writes only into
the task 2 output directory. No Provider call, no database, no production code.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
from decimal import Decimal
from pathlib import Path
from typing import Any

from w2.domain.admission_contract import economic_admission_pass
from w2.domain.canonical_serialization import HashDomain, canonical_bytes

# Loaded by path, not as a package: this research module lives outside src/w2 so
# nothing in the production tree can import it even by accident.
_CANDIDATE_PATH = Path(__file__).resolve().parent / (
    "official_candidate_confidence_shrinkage.py")
_candidate_spec = importlib.util.spec_from_file_location(
    "w2_official_candidate_confidence_shrinkage", _CANDIDATE_PATH)
assert _candidate_spec is not None and _candidate_spec.loader is not None
_candidate = importlib.util.module_from_spec(_candidate_spec)
_candidate_spec.loader.exec_module(_candidate)

(
    CANDIDATE_ID,
    CANDIDATE_SCHEMA,
    GRADE,
    MIN_TRAINING_ROWS,
    NOT_ESTIMABLE_MISSING_CASHFLOW_EDGE,
    NOT_ESTIMABLE_MISSING_DISTRIBUTION,
    NOT_ESTIMABLE_MISSING_EV_SE,
    NOT_ESTIMABLE_MISSING_ODDS,
    OBJECTIVE_PENALTY,
    STATES,
    T_GRID,
    apply_candidate,
    canonical_expected_value,
    conditional_graded,
    multiclass_brier,
    multiclass_log_loss,
    temporal_key,
) = (
    _candidate.CANDIDATE_ID,
    _candidate.CANDIDATE_SCHEMA,
    _candidate.GRADE,
    _candidate.MIN_TRAINING_ROWS,
    _candidate.NOT_ESTIMABLE_MISSING_CASHFLOW_EDGE,
    _candidate.NOT_ESTIMABLE_MISSING_DISTRIBUTION,
    _candidate.NOT_ESTIMABLE_MISSING_EV_SE,
    _candidate.NOT_ESTIMABLE_MISSING_ODDS,
    _candidate.OBJECTIVE_PENALTY,
    _candidate.STATES,
    _candidate.T_GRID,
    _candidate.apply_candidate,
    _candidate.canonical_expected_value,
    _candidate.conditional_graded,
    _candidate.multiclass_brier,
    _candidate.multiclass_log_loss,
    _candidate.temporal_key,
)

TASK_ID = "W2_OFFICIAL_CANDIDATE_ACCURACY_OPTIMIZATION_02"
BOOTSTRAP_ITERATIONS = 10_000
SEGMENTS = ("ALL_148", "FIRST_138", "LAST_10_INCIDENT_REPLAY", "ASIAN_HANDICAP", "TOTALS")
INPUT_FILES = (
    "OFFICIAL_148_SOURCE_BUNDLE.jsonl",
    "OFFICIAL_148_MANIFEST.jsonl",
    "LOSS_ROOT_CAUSE_REPORT.md",
    "CALIBRATION_COMPARISON.json",
    "METRICS.json",
    "HASHES.sha256",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rows(package: Path) -> list[dict[str, Any]]:
    manifest = [
        json.loads(line)
        for line in (package / "OFFICIAL_148_MANIFEST.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    rows: list[dict[str, Any]] = []
    for row in manifest:
        dist = row["model_settlement_distribution"] or {}
        ev, ev_minus_se = row["current_ev"], row["current_ev_minus_se"]
        rows.append({
            "evaluation_id": row["evaluation_id"],
            "fixture_id": row["fixture_id"],
            "market": row["market"],
            "selection": row["selection"],
            "exact_line": row["exact_line"],
            "decimal_odds": row["decimal_odds"],
            "kickoff_utc": row["kickoff_utc"],
            "evaluated_at": row["evaluated_at"],
            "result_available_at": row["result_available_at"],
            "settlement": row["settlement"],
            "profit_units": row["profit_units"],
            "cashflow_price_edge": row["current_cashflow_price_edge"],
            "cashflow_edge_provenance": row["cashflow_edge_provenance"],
            "factor_disposition": row["factor_disposition"],
            "lineup_status": row["lineup_status"],
            "ev": ev,
            "ev_se": (None if ev is None or ev_minus_se is None else ev - ev_minus_se),
            "ev_minus_se": ev_minus_se,
            "dist": {state: float(dist.get(state, 0.0)) for state in STATES},
        })
    return rows


def model_metrics(records: list[dict[str, Any]], key: str) -> dict[str, Any]:
    """Model-layer quality on every row, emitted or not. No selection here."""
    if not records:
        return {"rows": 0, "not_estimable_reason": "NO_ROWS"}
    decisive = [row for row in records if row["settlement"] != "PUSH"]
    predicted = (
        sum(conditional_graded(row[key]) for row in decisive) / len(decisive)
        if decisive else None
    )
    actual = (
        sum(GRADE[row["settlement"]] for row in decisive) / len(decisive)
        if decisive else None
    )
    return {
        "rows": len(records),
        "decisive_rows": len(decisive),
        "five_state_log_loss": round(
            sum(multiclass_log_loss(row[key], row["settlement"]) for row in records)
            / len(records), 6),
        "multiclass_brier": round(
            sum(multiclass_brier(row[key], row["settlement"]) for row in records)
            / len(records), 6),
        "predicted_graded_rate": None if predicted is None else round(predicted, 6),
        "actual_graded_rate": None if actual is None else round(actual, 6),
        # signed, predicted minus actual: positive means overconfident
        "calibration_error": (
            None if predicted is None else round(predicted - actual, 6)),
        "abs_calibration_error": (
            None if predicted is None else round(abs(predicted - actual), 6)),
        "mean_predicted_loss_probability": round(
            sum(float(row[key]["LOSS"]) for row in records) / len(records), 6),
        "mean_predicted_half_loss_probability": round(
            sum(float(row[key]["HALF_LOSS"]) for row in records) / len(records), 6),
        "settlement_counts": {
            state: sum(1 for row in records if row["settlement"] == state)
            for state in STATES
        },
    }


def calibration_bootstrap(
    records: list[dict[str, Any]], key: str, seed: int
) -> dict[str, Any]:
    """Fixture-clustered interval: both markets of a fixture resample together."""
    decisive = [row for row in records if row["settlement"] != "PUSH"]
    if not decisive:
        return {"interval": None, "reason": "NO_DECISIVE_ROWS"}
    by_fixture: dict[str, list[dict[str, Any]]] = {}
    for row in decisive:
        by_fixture.setdefault(row["fixture_id"], []).append(row)
    keys = sorted(by_fixture)
    rng = random.Random(seed)  # noqa: S311 - resampling, not cryptography
    gaps: list[float] = []
    for _ in range(BOOTSTRAP_ITERATIONS):
        picked = [rng.choice(keys) for _ in keys]
        sample = [row for pick in picked for row in by_fixture[pick]]
        predicted = sum(conditional_graded(row[key]) for row in sample) / len(sample)
        actual = sum(GRADE[row["settlement"]] for row in sample) / len(sample)
        gaps.append(actual - predicted)
    gaps.sort()
    low = int(0.025 * BOOTSTRAP_ITERATIONS)
    high = int(0.975 * BOOTSTRAP_ITERATIONS)
    return {
        "iterations": BOOTSTRAP_ITERATIONS,
        "cluster_unit": "fixture_id",
        "clusters": len(keys),
        "decisive_rows": len(decisive),
        "calibration_gap_ci95": [round(gaps[low], 6), round(gaps[high], 6)],
        "gap_ci_excludes_zero": gaps[high] < 0 or gaps[low] > 0,
    }


def not_estimable_reason(row: dict[str, Any]) -> str | None:
    """Why the recommendation layer cannot judge this row, or None when it can."""
    if row["cashflow_price_edge"] is None:
        return NOT_ESTIMABLE_MISSING_CASHFLOW_EDGE
    if row["ev_minus_se"] is None or row["ev_se"] is None:
        return NOT_ESTIMABLE_MISSING_EV_SE
    if row["decimal_odds"] is None:
        return NOT_ESTIMABLE_MISSING_ODDS
    if abs(sum(row["dist"].values()) - 1.0) > 1e-6:
        return NOT_ESTIMABLE_MISSING_DISTRIBUTION
    return None


def recommendation_layer(
    records: list[dict[str, Any]], key: str, universe: int
) -> dict[str, Any]:
    """What the candidate would have sent, only where the evidence supports it."""
    emitted: list[dict[str, Any]] = []
    blocked = 0
    reasons: dict[str, int] = {}
    estimable = 0
    for row in records:
        reason = not_estimable_reason(row)
        if reason is not None:
            reasons[reason] = reasons.get(reason, 0) + 1
            continue
        estimable += 1
        calibrated_ev = canonical_expected_value(row["decimal_odds"], row[key])
        if economic_admission_pass(
            expected_value=calibrated_ev,
            ev_minus_se=calibrated_ev - row["ev_se"],
            cashflow_price_edge=row["cashflow_price_edge"],
        ):
            emitted.append(row)
        else:
            blocked += 1
    summary: dict[str, Any] = {
        "universe_rows": universe,
        "estimable_rows": estimable,
        "candidate_emitted": len(emitted),
        "candidate_blocked": blocked,
        "coverage_of_universe": round(len(emitted) / universe, 6) if universe else None,
        "coverage_of_estimable": (
            round(len(emitted) / estimable, 6) if estimable else None),
        "not_estimable_rows": sum(reasons.values()),
        "not_estimable_reason_counts": dict(sorted(reasons.items())),
    }
    if not emitted:
        summary["settlement_counts"] = {state: 0 for state in STATES}
        summary["graded_hit_rate"] = None
        summary["profit_units"] = "0"
        summary["max_drawdown_units"] = "0"
        summary["max_consecutive_losing"] = 0
        summary["note"] = "NO_EMITTED_RECORDS_IS_NOT_AN_ACCURACY_RESULT"
        return summary
    decisive = [row for row in emitted if row["settlement"] != "PUSH"]
    running = peak = drawdown = Decimal(0)
    streak = worst = 0
    for row in emitted:
        running += Decimal(str(row["profit_units"]))
        peak = max(peak, running)
        drawdown = max(drawdown, peak - running)
        if row["settlement"] in {"LOSS", "HALF_LOSS"}:
            streak += 1
            worst = max(worst, streak)
        elif row["settlement"] != "PUSH":
            streak = 0
    summary["settlement_counts"] = {
        state: sum(1 for row in emitted if row["settlement"] == state)
        for state in STATES
    }
    summary["graded_hit_rate"] = (
        round(sum(GRADE[row["settlement"]] for row in decisive) / len(decisive), 6)
        if decisive else None)
    summary["profit_units"] = str(
        sum(Decimal(str(row["profit_units"])) for row in emitted))
    summary["max_drawdown_units"] = str(drawdown)
    summary["max_consecutive_losing"] = worst
    return summary


def segments_of(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    ordered = sorted(records, key=temporal_key)
    return {
        "ALL_148": ordered,
        "FIRST_138": ordered[:-10],
        "LAST_10_INCIDENT_REPLAY": ordered[-10:],
        "ASIAN_HANDICAP": [r for r in ordered if r["market"] == "ASIAN_HANDICAP"],
        "TOTALS": [r for r in ordered if r["market"] == "TOTALS"],
    }


def verdict(report: dict[str, Any]) -> dict[str, Any]:
    """The frozen pass criteria, each evaluated separately and reported as such."""
    all148 = report["segments"]["ALL_148"]
    first138 = report["segments"]["FIRST_138"]
    inc_all, cand_all = all148["incumbent"], all148["candidate"]
    inc_138, cand_138 = first138["incumbent"], first138["candidate"]
    rec = all148["recommendation_layer"]["candidate"]
    checks = {
        "1_all148_log_loss_strictly_lower": (
            cand_all["five_state_log_loss"] < inc_all["five_state_log_loss"]),
        "2_all148_brier_strictly_lower": (
            cand_all["multiclass_brier"] < inc_all["multiclass_brier"]),
        "3_first138_not_both_worse": not (
            cand_138["five_state_log_loss"] > inc_138["five_state_log_loss"]
            and cand_138["multiclass_brier"] > inc_138["multiclass_brier"]),
        "4_all148_abs_calibration_gap_falls": (
            cand_all["abs_calibration_error"] < inc_all["abs_calibration_error"]),
        "5_first138_abs_calibration_gap_falls": (
            cand_138["abs_calibration_error"] < inc_138["abs_calibration_error"]),
        "6_selection_line_odds_settlement_unchanged": report["invariants"][
            "selection_line_odds_settlement_unchanged"],
        "7_not_won_by_dropping_candidates": (
            rec["candidate_emitted"] > 0
            and rec["coverage_of_estimable"] is not None
            and rec["coverage_of_estimable"] >= 0.5),
        "8_recommendation_layer_reports_coverage_and_reasons": bool(
            rec.get("not_estimable_reason_counts") is not None
            and rec.get("coverage_of_estimable") is not None),
        "9_last10_is_incident_replay_only": report["last10_is_incident_replay_only"],
    }
    return {
        "checks": checks,
        "all_passed": all(checks.values()),
        "failed": sorted(name for name, ok in checks.items() if not ok),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package, output = args.package, args.output
    output.mkdir(parents=True, exist_ok=True)

    rows = load_rows(package)
    applied = apply_candidate(rows)
    seed = int.from_bytes(
        hashlib.sha256(canonical_bytes(
            {"task_id": TASK_ID, "candidate_id": CANDIDATE_ID},
            domain=HashDomain.FUTURE_REFRESH_EVIDENCE,
        )).digest()[:8], "big")

    report: dict[str, Any] = {
        "schema_version": "w2.official_candidate_accuracy_optimization.v1",
        "task_id": TASK_ID,
        "candidate_id": CANDIDATE_ID,
        "candidate_schema": CANDIDATE_SCHEMA,
        "universe_rows": len(applied),
        "bootstrap_seed": seed,
        "temperature_grid": {
            "min": T_GRID[0], "max": T_GRID[-1], "step": 0.01, "values": len(T_GRID)},
        "temperature_objective": (
            f"mean_multiclass_log_loss(T) + {OBJECTIVE_PENALTY} * (log T) ** 2"),
        "temperature_selection": "lowest objective; ties to nearest 1.00 then smaller T",
        "min_training_rows": MIN_TRAINING_ROWS,
        "training_axis": "GLOBAL_ALL_MARKETS_POOLED",
        "last10_is_incident_replay_only": True,
        "segments": {},
    }

    # Invariants: the candidate touched confidence and nothing else.
    by_id = {row["evaluation_id"]: row for row in rows}
    unchanged = all(
        (r["selection"], r["exact_line"], r["decimal_odds"], r["settlement"],
         r["profit_units"], r["market"], r["factor_disposition"], r["lineup_status"])
        == (o["selection"], o["exact_line"], o["decimal_odds"], o["settlement"],
            o["profit_units"], o["market"], o["factor_disposition"], o["lineup_status"])
        for r in applied
        for o in [by_id[r["evaluation_id"]]]
    )
    report["invariants"] = {
        "selection_line_odds_settlement_unchanged": unchanged,
        "rows_in": len(rows),
        "rows_out": len(applied),
        "distinct_fixtures": len({row["fixture_id"] for row in applied}),
        "total_profit_units": str(
            sum(Decimal(str(row["profit_units"])) for row in applied)),
    }

    for name, records in segments_of(applied).items():
        universe = len(records)
        report["segments"][name] = {
            "universe_rows": universe,
            "incumbent": model_metrics(records, "incumbent_dist"),
            "candidate": model_metrics(records, "candidate_dist"),
            "incumbent_calibration_bootstrap": calibration_bootstrap(
                records, "incumbent_dist", seed),
            "candidate_calibration_bootstrap": calibration_bootstrap(
                records, "candidate_dist", seed),
            "recommendation_layer": {
                "incumbent": recommendation_layer(records, "incumbent_dist", universe),
                "candidate": recommendation_layer(records, "candidate_dist", universe),
            },
        }

    report["verdict"] = verdict(report)
    report["model_candidate"] = (
        "READY" if report["verdict"]["all_passed"] else "NO_SAFE_CANDIDATE")

    temperature_log = {
        "schema_version": "w2.official_candidate_temperature_log.v1",
        "task_id": TASK_ID,
        "candidate_id": CANDIDATE_ID,
        "training_axis": "GLOBAL_ALL_MARKETS_POOLED",
        "min_training_rows": MIN_TRAINING_ROWS,
        "grid": {"min": T_GRID[0], "max": T_GRID[-1], "step": 0.01},
        "rows_at_neutral_temperature": sum(
            1 for row in applied if row["temperature"] == 1.00),
        "rows_at_grid_ceiling": sum(
            1 for row in applied if row["temperature"] == T_GRID[-1]),
        "distinct_temperatures": sorted({row["temperature"] for row in applied}),
        "records": [
            {
                "evaluation_id": row["evaluation_id"],
                "market": row["market"],
                "evaluated_at": row["evaluated_at"],
                "result_knowledge_cutoff": row["result_knowledge_cutoff"],
                "training_rows": row["training_rows"],
                "temperature": row["temperature"],
                "incumbent_dist": {k: round(v, 12) for k, v in row["incumbent_dist"].items()},
                "candidate_dist": {k: round(v, 12) for k, v in row["candidate_dist"].items()},
            }
            for row in applied
        ],
    }

    source_identity = {
        "schema_version": "w2.official_candidate_optimization_source_identity.v1",
        "task_id": TASK_ID,
        "input_package": str(package),
        "input_files_sha256": {
            name: sha256_file(package / name) for name in INPUT_FILES},
        "provider_calls": 0,
        "public_http_fetch": 0,
        "production_db_reads": 0,
        "production_db_writes": 0,
        "deployment_executed": False,
        "obsidian_writes": 0,
    }

    (output / "CANDIDATE_METRICS.json").write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    (output / "CANDIDATE_TEMPERATURE_LOG.json").write_text(
        json.dumps(temperature_log, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    (output / "SOURCE_IDENTITY.json").write_text(
        json.dumps(source_identity, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "model_candidate": report["model_candidate"],
        "failed_checks": report["verdict"]["failed"],
        "all_148": {
            "incumbent": {k: report["segments"]["ALL_148"]["incumbent"][k]
                          for k in ("five_state_log_loss", "multiclass_brier",
                                    "abs_calibration_error")},
            "candidate": {k: report["segments"]["ALL_148"]["candidate"][k]
                          for k in ("five_state_log_loss", "multiclass_brier",
                                    "abs_calibration_error")},
        },
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
