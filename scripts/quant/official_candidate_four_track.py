"""Task D: four-track result-oriented comparison on the 148 official candidates.

Offline research only. Reuses the production canonical Decimal five-state EV
authority and the production economic admission contract; it never defines a
second settlement or EV formula, and it never touches the production chain.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from decimal import Decimal
from pathlib import Path
from typing import Any

from w2.domain.admission_contract import economic_admission_pass
from w2.domain.canonical_serialization import HashDomain, canonical_bytes
from w2.domain.five_state_pricing import (
    PROBABILITY_TOLERANCE,
    SettlementDistribution,
    expected_value,
)

TASK_ID = "W2_OFFICIAL_CANDIDATE_ACCURACY_REMEDIATION_01"
STATES = ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")
GRADE = {"WIN": 1.0, "HALF_WIN": 0.5, "HALF_LOSS": 0.0, "LOSS": 0.0}
MIN_TRAIN = 20
BOOTSTRAP_ITERATIONS = 10_000
TRACKS = (
    "INCUMBENT",
    "AH_FACTOR_VETO_ONLY",
    "ROLLING_TEMPERATURE_ONLY",
    "AH_FACTOR_VETO_PLUS_ROLLING_TEMPERATURE",
)
# Frozen before any track result was inspected.
T_GRID = tuple(round(0.70 + i * 0.01, 2) for i in range(int(round((2.00 - 0.70) / 0.01)) + 1))


def temper(dist: dict[str, float], temperature: float) -> dict[str, float]:
    """Temperature-scale and renormalise a five-state distribution."""
    logits = [math.log(max(float(dist.get(k, 0.0)), 1e-12)) / temperature for k in STATES]
    peak = max(logits)
    weights = [math.exp(x - peak) for x in logits]
    total = sum(weights)
    return {k: w / total for k, w in zip(STATES, weights, strict=True)}


def _conditional_graded(dist: dict[str, float]) -> float:
    """Predicted graded win rate conditional on the bet not pushing."""
    push = dist.get("PUSH", 0.0)
    if push >= 1.0:
        return 0.0
    return (dist.get("WIN", 0.0) + 0.5 * dist.get("HALF_WIN", 0.0)) / (1.0 - push)


def multiclass_log_loss(dist: dict[str, float], settlement: str) -> float:
    return -math.log(max(dist.get(settlement, 0.0), 1e-12))


def multiclass_brier(dist: dict[str, float], settlement: str) -> float:
    return sum((dist.get(k, 0.0) - (1.0 if k == settlement else 0.0)) ** 2 for k in STATES)


def fit_temperature(training: list[dict]) -> float:
    """Grid search with the frozen penalty and tie-break; T=1.00 below MIN_TRAIN."""
    if len(training) < MIN_TRAIN:
        return 1.00
    best: tuple[float, float] | None = None
    for temperature in T_GRID:
        losses = [
            multiclass_log_loss(temper(row["dist"], temperature), row["settlement"])
            for row in training
        ]
        objective = sum(losses) / len(losses) + 0.10 * (math.log(temperature) ** 2)
        if best is None:
            best = (temperature, objective)
            continue
        current_t, current_obj = best
        if objective < current_obj - 1e-15:
            best = (temperature, objective)
        elif abs(objective - current_obj) <= 1e-15:
            # Tie-break: nearest to 1.00, then the smaller value.
            challenger = (abs(temperature - 1.00), temperature)
            incumbent = (abs(current_t - 1.00), current_t)
            if challenger < incumbent:
                best = (temperature, objective)
    assert best is not None
    return best[0]


def distribution_from(dist: dict[str, float]) -> SettlementDistribution:
    raw = SettlementDistribution(
        full_win_probability=Decimal(str(dist["WIN"])),
        half_win_probability=Decimal(str(dist["HALF_WIN"])),
        push_probability=Decimal(str(dist["PUSH"])),
        half_loss_probability=Decimal(str(dist["HALF_LOSS"])),
        full_loss_probability=Decimal(str(dist["LOSS"])),
    ).normalized()
    total = sum(
        (getattr(raw, f) for f in raw.__dataclass_fields__), Decimal(0)
    )
    if abs(total - 1) > PROBABILITY_TOLERANCE:
        raise ValueError("CALIBRATED_DISTRIBUTION_FAILED_1E9_CONTRACT")
    return raw


def build_tracks(rows: list[dict]) -> dict[str, list[dict]]:
    """Emit, per track, the records that would still have been recommended."""
    ordered = sorted(rows, key=lambda r: (r["evaluated_at"], r["kickoff_utc"], r["evaluation_id"]))
    out: dict[str, list[dict]] = {name: [] for name in TRACKS}
    temperature_log: list[dict] = []
    for index, row in enumerate(ordered):
        # D1 temporal contract: only records already authoritatively settled
        # before this record was evaluated may train it.
        training = [
            {"dist": other["dist"], "settlement": other["settlement"]}
            for other in ordered[:index]
            if other["result_available_at"] < row["evaluated_at"]
            and other["market"] == row["market"]
        ]
        temperature = fit_temperature(training)
        temperature_log.append({
            "evaluation_id": row["evaluation_id"], "market": row["market"],
            "training_rows": len(training), "temperature": temperature,
        })
        calibrated = temper(row["dist"], temperature)
        calibrated_ev = float(expected_value(
            Decimal(str(row["decimal_odds"])), distribution_from(calibrated)))
        # Uncertainty is never allowed to shrink: reuse the original ev_se.
        original_se = row["ev_se"]
        calibrated_ev_minus_se = (
            None if original_se is None else calibrated_ev - original_se)
        calibrated_pass = (
            economic_admission_pass(
                expected_value=calibrated_ev,
                ev_minus_se=calibrated_ev_minus_se,
                cashflow_price_edge=row["cashflow_price_edge"],
            ) if original_se is not None else False
        )
        # AH factor verdict was never persisted, so the veto track cannot be
        # evaluated on identity. The conservative bound blocks every AH record.
        factor_blocked = row["market"] == "ASIAN_HANDICAP"
        enriched = {**row, "temperature": temperature, "calibrated_ev": calibrated_ev,
                    "calibrated_ev_minus_se": calibrated_ev_minus_se,
                    "calibrated_admission": calibrated_pass}
        out["INCUMBENT"].append(enriched)
        if not factor_blocked:
            out["AH_FACTOR_VETO_ONLY"].append(enriched)
        if calibrated_pass:
            out["ROLLING_TEMPERATURE_ONLY"].append(enriched)
        if calibrated_pass and not factor_blocked:
            out["AH_FACTOR_VETO_PLUS_ROLLING_TEMPERATURE"].append(enriched)
    return out, temperature_log


def metrics(emitted: list[dict], universe: int) -> dict[str, Any]:
    if not emitted:
        return {"emitted": 0, "coverage": 0.0, "not_estimable_reason": "NO_EMITTED_RECORDS"}
    counts = {s: sum(1 for r in emitted if r["settlement"] == s) for s in STATES}
    decisive = [r for r in emitted if r["settlement"] != "PUSH"]
    profit = sum(Decimal(str(r["profit_units"])) for r in emitted)
    running = Decimal(0)
    peak = Decimal(0)
    drawdown = Decimal(0)
    streak = 0
    worst_streak = 0
    for row in emitted:
        running += Decimal(str(row["profit_units"]))
        peak = max(peak, running)
        drawdown = max(drawdown, peak - running)
        if row["settlement"] in {"LOSS", "HALF_LOSS"}:
            streak += 1
            worst_streak = max(worst_streak, streak)
        elif row["settlement"] != "PUSH":
            streak = 0
    return {
        "emitted": len(emitted),
        "coverage": round(len(emitted) / universe, 6),
        "settlement_counts": counts,
        "full_loss_rate": round(counts["LOSS"] / len(emitted), 6),
        "graded_hit_rate": (
            round(sum(GRADE[r["settlement"]] for r in decisive) / len(decisive), 6)
            if decisive else None),
        "profit_units": str(profit),
        "five_state_log_loss": round(
            sum(multiclass_log_loss(r["dist_used"], r["settlement"]) for r in emitted)
            / len(emitted), 6),
        "multiclass_brier": round(
            sum(multiclass_brier(r["dist_used"], r["settlement"]) for r in emitted)
            / len(emitted), 6),
        # Calibration error uses the decisive subset only, with the predicted
        # graded win rate renormalised to exclude PUSH, matching the grading rule.
        "calibration_error": (
            round((sum(_conditional_graded(r["dist_used"]) for r in decisive)
                   - sum(GRADE[r["settlement"]] for r in decisive)) / len(decisive), 6)
            if decisive else None),
        "predicted_graded_rate": (
            round(sum(_conditional_graded(r["dist_used"]) for r in decisive) / len(decisive), 6)
            if decisive else None),
        "max_consecutive_losing": worst_streak,
        "max_drawdown_units": str(drawdown),
    }


def bootstrap(emitted: list[dict], fixtures: list[str], seed: int) -> dict[str, Any]:
    if not emitted:
        return {"interval": None, "reason": "NO_EMITTED_RECORDS"}
    by_fixture: dict[str, list[dict]] = {}
    for row in emitted:
        by_fixture.setdefault(row["fixture_id"], []).append(row)
    keys = sorted(by_fixture)
    rng = random.Random(seed)  # noqa: S311 - resampling, not cryptography
    totals: list[float] = []
    for _ in range(BOOTSTRAP_ITERATIONS):
        picked = [rng.choice(keys) for _ in keys]
        totals.append(sum(
            float(row["profit_units"]) for key in picked for row in by_fixture[key]))
    totals.sort()
    return {
        "iterations": BOOTSTRAP_ITERATIONS,
        "cluster_unit": "fixture_id",
        "clusters": len(keys),
        "profit_units_p2_5": round(totals[int(0.025 * BOOTSTRAP_ITERATIONS)], 4),
        "profit_units_p50": round(totals[int(0.5 * BOOTSTRAP_ITERATIONS)], 4),
        "profit_units_p97_5": round(totals[int(0.975 * BOOTSTRAP_ITERATIONS)], 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()
    pkg = args.package
    manifest = [json.loads(line) for line in
                (pkg / "OFFICIAL_148_MANIFEST.jsonl").read_text().splitlines() if line.strip()]
    times = {r["fixture_id"]: r["result_available_at"]
             for r in json.loads((pkg / "_result_times.json").read_text())}
    rows = []
    for row in manifest:
        dist = row["model_settlement_distribution"] or {}
        ev = row["current_ev"]
        ev_minus_se = row["current_ev_minus_se"]
        rows.append({
            "evaluation_id": row["evaluation_id"], "fixture_id": row["fixture_id"],
            "market": row["market"], "selection": row["selection"],
            "kickoff_utc": row["kickoff_utc"], "evaluated_at": row["evaluated_at"],
            "result_available_at": times[row["fixture_id"]],
            "settlement": row["settlement"], "profit_units": row["profit_units"],
            "decimal_odds": row["decimal_odds"],
            "cashflow_price_edge": row["current_cashflow_price_edge"],
            "ev": ev,
            "ev_se": (None if ev is None or ev_minus_se is None else ev - ev_minus_se),
            "dist": {s: float(dist.get(s, 0.0)) for s in STATES},
        })
    tracks, temperature_log = build_tracks(rows)
    seed = int.from_bytes(hashlib.sha256(
        canonical_bytes({"task_id": TASK_ID}, domain=HashDomain.FUTURE_REFRESH_EVIDENCE)
    ).digest()[:8], "big")
    universe = len(rows)
    report: dict[str, Any] = {
        "schema_version": "w2.official_candidate_four_track.v1",
        "task_id": TASK_ID,
        "universe_rows": universe,
        "bootstrap_seed": seed,
        "temperature_grid": {"min": T_GRID[0], "max": T_GRID[-1], "step": 0.01,
                             "size": len(T_GRID)},
        "temperature_objective": "mean_multiclass_log_loss + 0.10 * (log T) ** 2",
        "min_training_rows_per_market_axis": MIN_TRAIN,
        "factor_identity_coverage": {
            "reconstructible": 0, "unknown_not_reconstructible": universe,
            "status": "NOT_ESTIMABLE_FACTOR_IDENTITY",
            "treatment": "AH_FACTOR_VETO_ONLY and the combined track use the conservative "
                         "bound that blocks every ASIAN_HANDICAP record, because the factor "
                         "verdict was never persisted. This is the pessimistic choice for "
                         "coverage and was fixed before any track result was read.",
        },
        "tracks": {},
    }
    for name in TRACKS:
        emitted = tracks[name]
        for row in emitted:
            row["dist_used"] = (
                temper(row["dist"], row["temperature"])
                if "TEMPERATURE" in name else row["dist"])
        report["tracks"][name] = {
            **metrics(emitted, universe),
            "bootstrap": bootstrap(emitted, [], seed),
        }
    report["temperature_selection"] = {
        "distinct_temperatures": sorted({t["temperature"] for t in temperature_log}),
        "rows_at_default_T1": sum(1 for t in temperature_log if t["temperature"] == 1.00),
    }
    (pkg / "CALIBRATION_COMPARISON.json").write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({n: {k: v for k, v in report["tracks"][n].items()
                          if k in ("emitted", "coverage", "profit_units", "graded_hit_rate",
                                   "full_loss_rate", "five_state_log_loss")}
                      for n in TRACKS}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
