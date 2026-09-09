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
from datetime import UTC, datetime
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
# Tracks that cannot be estimated at all: the historical factor verdict was never
# persisted (0/148), so no factor-veto counterfactual has an identity to stand on.
FACTOR_DEPENDENT_TRACKS = ("AH_FACTOR_VETO_ONLY",
                           "AH_FACTOR_VETO_PLUS_ROLLING_TEMPERATURE")
# Diagnostic only. Deleting the whole AH market is NOT a factor-veto counterfactual
# and must never be used to judge whether the bypass was the main cause.
DIAGNOSTIC_TRACK = "ALL_AH_BLOCKED_CONSERVATIVE_BOUND"
SEGMENTS = ("ALL_148", "FIRST_138", "LAST_10_INCIDENT_REPLAY")
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
    """Freeze a tempered distribution into the canonical Decimal five-state type.

    The tolerance is checked on the way in as well as on the way out.
    ``normalized()`` divides by the total, so it would silently rescale a
    distribution that had drifted; checking only afterwards can never fail and
    would turn the 1e-9 contract into a no-op.
    """
    incoming = sum(Decimal(str(dist[state])) for state in STATES)
    if abs(incoming - 1) > PROBABILITY_TOLERANCE:
        raise ValueError("CALIBRATED_DISTRIBUTION_FAILED_1E9_CONTRACT")
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


# Chronology everywhere comes from parsed instants, never from text.
_FAR_FUTURE = datetime.max.replace(tzinfo=UTC)


def _temporal_key(row: dict) -> tuple[datetime, datetime, str]:
    return (
        utc(row.get("evaluated_at")) or _FAR_FUTURE,
        utc(row.get("kickoff_utc")) or _FAR_FUTURE,
        str(row.get("evaluation_id") or ""),
    )


def utc(value: object) -> datetime | None:
    """Parse a timestamp to an aware UTC datetime, or None when it is unusable.

    The two fields being compared do not share a spelling: the settlement time
    arrives from a Postgres timestamptz as ``2026-08-20 02:36:31.442008+00``
    while the evaluation time arrives as ``2026-08-20T00:22:32.149069Z``.
    Comparing those as text compares ``' '`` (0x20) against ``'T'`` (0x54) at
    index 10, so every space-separated result sorts before every T-separated
    evaluation whatever the actual instants are -- which is how 412 pairs of
    future results reached the training window. Nothing here may compare
    timestamps as strings.

    A naive value is read as UTC: every timestamp in this corpus comes from a
    UTC column. Anything unparseable is None, and the caller fails closed.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def trainable_for(other: dict, row: dict) -> bool:
    """Whether `other` may train the temperature used on `row`.

    Four ways to fail, all of them leakage: the result time is unknown or
    unparseable, the evaluation time is, the two are different market axes, or
    the result was not authoritatively available strictly before the row was
    evaluated -- a result landing at the same instant is not yet knowledge.
    """
    if other.get("market") != row.get("market"):
        return False
    available = utc(other.get("result_available_at"))
    evaluated = utc(row.get("evaluated_at"))
    if available is None or evaluated is None:
        return False
    return available < evaluated


def build_tracks(rows: list[dict]) -> tuple[dict[str, list[dict]], list[dict]]:
    """Emit, per estimable track, the records that would still have been sent."""
    ordered = sorted(rows, key=_temporal_key)
    out: dict[str, list[dict]] = {"INCUMBENT": [], "ROLLING_TEMPERATURE_ONLY": [],
                                  DIAGNOSTIC_TRACK: []}
    temperature_log: list[dict] = []
    for index, row in enumerate(ordered):
        # D1 temporal contract: only records already authoritatively settled
        # before this record was evaluated may train it. A record with no
        # authoritative result time is not "not yet settled" -- it is unknown,
        # so it is excluded rather than compared, which would also have raised
        # on the None.
        training = [
            {"dist": other["dist"], "settlement": other["settlement"]}
            for other in ordered[:index]
            if trainable_for(other, row)
        ]
        temperature = fit_temperature(training)
        temperature_log.append({
            "evaluation_id": row["evaluation_id"], "market": row["market"],
            "training_rows": len(training), "temperature": temperature,
            "result_knowledge_cutoff": row["evaluated_at"],
        })
        calibrated = temper(row["dist"], temperature)
        calibrated_ev = float(expected_value(
            Decimal(str(row["decimal_odds"])), distribution_from(calibrated)))
        original_se = row["ev_se"]
        calibrated_ev_minus_se = (
            None if original_se is None else calibrated_ev - original_se)
        # R5: a missing cashflow edge is absent evidence, never a refusal.
        if row["cashflow_price_edge"] is None:
            temperature_status = "NOT_ESTIMABLE_MISSING_CASHFLOW_EDGE"
            calibrated_pass = None
        elif original_se is None:
            temperature_status = "NOT_ESTIMABLE_MISSING_EV_SE"
            calibrated_pass = None
        else:
            calibrated_pass = economic_admission_pass(
                expected_value=calibrated_ev,
                ev_minus_se=calibrated_ev_minus_se,
                cashflow_price_edge=row["cashflow_price_edge"])
            temperature_status = "EMITTED" if calibrated_pass else "BLOCKED_BY_CALIBRATION"
        enriched = {**row, "temperature": temperature, "calibrated_ev": calibrated_ev,
                    "calibrated_ev_minus_se": calibrated_ev_minus_se,
                    "temperature_status": temperature_status}
        out["INCUMBENT"].append(enriched)
        if calibrated_pass:
            out["ROLLING_TEMPERATURE_ONLY"].append(enriched)
        if row["market"] != "ASIAN_HANDICAP":
            out[DIAGNOSTIC_TRACK].append(enriched)
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


def calibration_bootstrap(rows: list[dict], seed: int) -> dict[str, Any]:
    """R9: fixture-clustered interval for the overall calibration gap.

    Both markets of one fixture are resampled together, so the AH and TOTALS
    records of the same match never enter independently.
    """
    decisive = [r for r in rows if r["settlement"] != "PUSH"]
    if not decisive:
        return {"interval": None, "reason": "NO_DECISIVE_ROWS"}
    by_fixture: dict[str, list[dict]] = {}
    for row in decisive:
        by_fixture.setdefault(row["fixture_id"], []).append(row)
    keys = sorted(by_fixture)
    rng = random.Random(seed)  # noqa: S311 - resampling, not cryptography
    gaps: list[float] = []
    hits: list[float] = []
    for _ in range(BOOTSTRAP_ITERATIONS):
        picked = [rng.choice(keys) for _ in keys]
        sample = [row for key in picked for row in by_fixture[key]]
        predicted = sum(_conditional_graded(r["dist"]) for r in sample) / len(sample)
        actual = sum(GRADE[r["settlement"]] for r in sample) / len(sample)
        gaps.append(actual - predicted)
        hits.append(actual)
    gaps.sort()
    hits.sort()
    predicted_all = sum(_conditional_graded(r["dist"]) for r in decisive) / len(decisive)
    actual_all = sum(GRADE[r["settlement"]] for r in decisive) / len(decisive)
    lo = int(0.025 * BOOTSTRAP_ITERATIONS)
    hi = int(0.975 * BOOTSTRAP_ITERATIONS)
    return {
        "iterations": BOOTSTRAP_ITERATIONS, "cluster_unit": "fixture_id",
        "clusters": len(keys), "decisive_rows": len(decisive),
        "predicted_graded_rate": round(predicted_all, 6),
        "actual_graded_rate": round(actual_all, 6),
        "calibration_gap_point": round(actual_all - predicted_all, 6),
        "calibration_gap_ci95": [round(gaps[lo], 6), round(gaps[hi], 6)],
        "actual_graded_rate_ci95": [round(hits[lo], 6), round(hits[hi], 6)],
        "gap_ci_excludes_zero": gaps[hi] < 0 or gaps[lo] > 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()
    pkg = args.package
    manifest = [json.loads(line) for line in
                (pkg / "OFFICIAL_148_MANIFEST.jsonl").read_text().splitlines() if line.strip()]
    rows = []
    for row in manifest:
        dist = row["model_settlement_distribution"] or {}
        ev, ev_minus_se = row["current_ev"], row["current_ev_minus_se"]
        rows.append({
            "evaluation_id": row["evaluation_id"], "fixture_id": row["fixture_id"],
            "market": row["market"], "selection": row["selection"],
            "kickoff_utc": row["kickoff_utc"], "evaluated_at": row["evaluated_at"],
            # R6: read from the committed manifest, never an untracked side file.
            "result_available_at": row["result_available_at"],
            "settlement": row["settlement"], "profit_units": row["profit_units"],
            "decimal_odds": row["decimal_odds"],
            "cashflow_price_edge": row["current_cashflow_price_edge"],
            "cashflow_edge_provenance": row["cashflow_edge_provenance"],
            "ev": ev,
            "ev_se": (None if ev is None or ev_minus_se is None else ev - ev_minus_se),
            "dist": {s: float(dist.get(s, 0.0)) for s in STATES},
        })
    tracks, temperature_log = build_tracks(rows)
    seed = int.from_bytes(hashlib.sha256(canonical_bytes(
        {"task_id": TASK_ID}, domain=HashDomain.FUTURE_REFRESH_EVIDENCE)).digest()[:8], "big")
    ordered = sorted(rows, key=_temporal_key)
    segments = {"ALL_148": ordered, "FIRST_138": ordered[:-10],
                "LAST_10_INCIDENT_REPLAY": ordered[-10:]}
    report: dict[str, Any] = {
        "schema_version": "w2.official_candidate_four_track.v2",
        "task_id": TASK_ID, "universe_rows": len(rows), "bootstrap_seed": seed,
        "temperature_grid": {"min": T_GRID[0], "max": T_GRID[-1], "step": 0.01,
                             "size": len(T_GRID),
                             "frozen_before_results": True,
                             "grid_extended_after_hitting_ceiling": False},
        "temperature_objective": "mean_multiclass_log_loss + 0.10 * (log T) ** 2",
        "min_training_rows_per_market_axis": MIN_TRAIN,
        "factor_identity_coverage": {
            "reconstructible": 0, "unknown_not_reconstructible": len(rows)},
        "track_status": {
            "INCUMBENT": "ESTIMABLE",
            "AH_FACTOR_VETO_ONLY": "NOT_ESTIMABLE_FACTOR_IDENTITY",
            "ROLLING_TEMPERATURE_ONLY": "ESTIMABLE_ON_CASHFLOW_COMPLETE_SUBSET",
            "AH_FACTOR_VETO_PLUS_ROLLING_TEMPERATURE": "NOT_ESTIMABLE_FACTOR_IDENTITY",
            DIAGNOSTIC_TRACK: "DIAGNOSTIC_ONLY_NOT_A_FACTOR_VETO_COUNTERFACTUAL",
        },
        "diagnostic_track_caveat": (
            "ALL_AH_BLOCKED_CONSERVATIVE_BOUND simply deletes every ASIAN_HANDICAP "
            "record. It is not a factor-veto counterfactual and must not be used to "
            "decide whether the bypass was the main cause."),
        "segments": {},
    }
    for segment, subset in segments.items():
        ids = {r["evaluation_id"] for r in subset}
        entry: dict[str, Any] = {"universe_rows": len(subset)}
        for name in (*TRACKS, DIAGNOSTIC_TRACK):
            if name in FACTOR_DEPENDENT_TRACKS:
                entry[name] = {"status": "NOT_ESTIMABLE_FACTOR_IDENTITY",
                               "reason": "historical factor verdict was never persisted "
                                         "(0/148); no counterfactual identity exists",
                               "universe_rows": len(subset), "estimable_rows": 0}
                continue
            emitted = [r for r in tracks[name] if r["evaluation_id"] in ids]
            for row in emitted:
                row["dist_used"] = (temper(row["dist"], row["temperature"])
                                    if "TEMPERATURE" in name else row["dist"])
            if name == "ROLLING_TEMPERATURE_ONLY":
                estimable = [r for r in subset if r["cashflow_price_edge"] is not None]
                not_estimable = len(subset) - len(estimable)
                entry[name] = {
                    "status": "ESTIMABLE_ON_CASHFLOW_COMPLETE_SUBSET",
                    "universe_rows": len(subset), "estimable_rows": len(estimable),
                    "not_estimable_reason_counts": {
                        "NOT_ESTIMABLE_MISSING_CASHFLOW_EDGE": not_estimable},
                    "coverage_of_universe": round(len(emitted) / max(1, len(subset)), 6),
                    "coverage_of_estimable": (
                        round(len(emitted) / len(estimable), 6) if estimable else None),
                    **metrics(emitted, max(1, len(subset))),
                    "bootstrap": bootstrap(emitted, [], seed)}
            else:
                entry[name] = {"status": report["track_status"][name],
                               "universe_rows": len(subset),
                               "estimable_rows": len(emitted),
                               **metrics(emitted, max(1, len(subset))),
                               "bootstrap": bootstrap(emitted, [], seed)}
        entry["calibration"] = calibration_bootstrap(subset, seed)
        report["segments"][segment] = entry
    report["temperature_selection"] = {
        "distinct_temperatures": sorted({t["temperature"] for t in temperature_log}),
        "rows_at_T_1_00": sum(1 for t in temperature_log if t["temperature"] == 1.00),
        "rows_at_T_2_00_ceiling": sum(1 for t in temperature_log if t["temperature"] == 2.00),
        "log": temperature_log,
    }
    report["posthoc_note"] = {
        "high_confidence_bucket": "POSTHOC_EXPLORATORY",
        "reason": "the [0.65,1.01) slice was chosen after seeing results and is not a "
                  "preregistered gate",
    }
    (pkg / "CALIBRATION_COMPARISON.json").write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    for segment in SEGMENTS:
        cal = report["segments"][segment]["calibration"]
        print(f"{segment}: gap={cal['calibration_gap_point']} "
              f"CI95={cal['calibration_gap_ci95']} excl0={cal['gap_ci_excludes_zero']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
