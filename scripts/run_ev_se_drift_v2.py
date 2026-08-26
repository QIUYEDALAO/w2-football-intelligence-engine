#!/usr/bin/env python3
"""Frozen-protocol runner for EV-SE drift v2. Emits evidence and verifies it.

  --emit    write the evidence JSON
  --check   regenerate in memory and compare byte-for-byte (non-zero on any diff)
  --self-test-mutants   prove the invariant tests can actually fail
"""
from __future__ import annotations

import hashlib
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(__file__))
import ev_se_variogram as V
from _load import CORPUS_SHA256, CSV, load

EVIDENCE = os.path.join(
    os.path.dirname(__file__), "..", "docs", "review_packages",
    "EV_SE_DRIFT_V2", "EV_SE_DRIFT_V2_EVIDENCE.json",
)
HOLDOUT_EPOCH_DAYS = 20089.0  # 2026-01-01


def _round(x: float | None, k: int = 9) -> float | None:
    return None if x is None else round(x, k)


def estimate() -> tuple[dict[str, dict[str, object]], dict[tuple[str, str], float]]:
    cells: dict[str, dict[str, object]] = {}
    tau2: dict[tuple[str, str], float] = {}
    for comp in ("attack", "defence"):
        for league, rows in V.variogram_pairs(load(comp)).items():
            teams = {t for t, _, _ in rows}
            span = max(d for _, d, _ in rows)
            stats = V.team_stats(rows)
            intercept, slope = V.solve(stats, sorted(stats))
            lo, hi = V.bootstrap(stats)
            if intercept is None or slope is None:
                cells[f"{league}|{comp}"] = {"status": "INSUFFICIENT_SUPPORT", "use": False}
                continue
            tau2[(league, comp)] = intercept / 2
            if len(teams) < V.MIN_TEAMS or len(rows) < V.MIN_PAIRS or span < V.MIN_DELTA_SPAN:
                status = "INSUFFICIENT_SUPPORT"
            elif slope < 0:
                status = "NEGATIVE_SLOPE"
            elif lo is not None and lo > 0:
                status = "USABLE"
            else:
                status = "CI_INCLUDES_ZERO"
            cells[f"{league}|{comp}"] = {
                "teams": len(teams), "pairs": len(rows), "delta_span_days": _round(span, 3),
                "tau2": _round(intercept / 2), "alpha_abs": _round(slope),
                "ci_low": _round(lo), "ci_high": _round(hi),
                "status": status, "use": status == "USABLE",
            }
    return cells, tau2


def path_c(tau2: dict[tuple[str, str], float]) -> dict[str, dict[str, object]]:
    out: dict[str, list[float]] = {}
    for comp in ("attack", "defence"):
        for (league, _team, _season), series in load(comp, estimation_only=False).items():
            s = sorted(series)
            for i, (t, actual) in enumerate(s):
                if t < HOLDOUT_EPOCH_DAYS:
                    continue
                hist = [y for _, y in s[:i]][-20:]
                if len(hist) < 3:
                    continue
                se0 = statistics.stdev(hist) / (len(hist) ** 0.5)
                total = se0**2 + tau2[(league, comp)]
                mean = sum(hist) / len(hist)
                out.setdefault(f"{league}|{comp}", []).append((actual - mean) / total**0.5)
    report: dict[str, dict[str, object]] = {}
    for key, z in sorted(out.items()):
        n = len(z)
        if n < 30:
            continue
        c68 = sum(1 for x in z if abs(x) <= 1.0) / n
        c95 = sum(1 for x in z if abs(x) <= 1.96) / n
        def inside(p: float, nominal: float, count: int = n) -> bool:
            se = (p * (1 - p) / count) ** 0.5
            return bool(p - 1.96 * se <= nominal <= p + 1.96 * se)

        ok = inside(c68, 0.68) and inside(c95, 0.95)
        report[key] = {
            "n": n, "var_z": _round(sum(x * x for x in z) / n),
            "coverage_68": _round(c68), "coverage_95": _round(c95),
            "status": "OK" if ok else "PATH_C_MISMATCH",
        }
    return report


def xg_csv_fingerprint() -> dict[str, object]:
    """Fingerprint, row count and kickoff range of the read-only xG extract."""
    digest = hashlib.sha256()
    rows, lo, hi = 0, None, None
    with open(CSV, "rb") as fh:
        for raw in fh:
            digest.update(raw)
            parts = raw.decode().rstrip("\n").split(",")
            if len(parts) != 7 or parts[0] in ("BEGIN", "ROLLBACK"):
                continue
            rows += 1
            lo = parts[2] if lo is None or parts[2] < lo else lo
            hi = parts[2] if hi is None or parts[2] > hi else hi
    return {
        "xg_csv_sha256": digest.hexdigest(),
        "xg_csv_data_rows": rows,
        "xg_kickoff_min": lo,
        "xg_kickoff_max": hi,
    }


def build() -> dict[str, object]:
    cells, tau2 = estimate()
    return {
        "schema_version": "w2.ev_se.drift_v2.evidence.v1",
        "protocol_commit": "3fca0384",
        "inputs": {
            "corpus_sha256": CORPUS_SHA256,
            "holdout_cutoff": "2026-01-01",
            **xg_csv_fingerprint(),
        },
        "bootstrap": {"reps": V.REPS, "seed": V.SEED, "ci": V.CI},
        "alpha_cells": cells,
        "path_c": path_c(tau2),
        "forbidden_uses": ["SETTLED_PICK_PROFIT", "HIT_RATE", "CURRENT_65_PICKS"],
    }


def render(doc: dict[str, object]) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else "--check"
    if arg == "--self-test-mutants":
        return self_test_mutants()
    text = render(build())
    if arg == "--emit":
        with open(EVIDENCE, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(json.dumps({"emitted": hashlib.sha256(text.encode()).hexdigest()[:16]}))
        return 0
    with open(EVIDENCE, encoding="utf-8") as fh:
        stored = fh.read()
    if stored != text:
        print("EV_SE_DRIFT_V2_EVIDENCE_DIFF", file=sys.stderr)
        return 1
    print(json.dumps({"reproduction": "PASS"}))
    return 0


# ---- invariants and the mutants that must break them -------------------------
def se_formula(
    se0: float,
    age: float,
    coverage: float | None,
    *,
    alpha: float,
    beta: float,
    reset_age: bool = False,
    constant_inflation: float = 0.0,
    coverage_sign: float = 1.0,
    fail_open: bool = False,
) -> float | None:
    if coverage is None:
        if not fail_open:
            return None
        coverage = 1.0   # mutant: pretend full coverage, i.e. stay confident
    a = 0.0 if reset_age else age
    total = se0**2 + alpha * a + coverage_sign * beta * (1 - coverage)
    return float((total + constant_inflation) ** 0.5)


def invariants(
    *,
    alpha: float,
    beta: float,
    reset_age: bool = False,
    constant_inflation: float = 0.0,
    coverage_sign: float = 1.0,
    fail_open: bool = False,
) -> list[str]:
    knobs = {
        "alpha": alpha,
        "beta": beta,
        "reset_age": reset_age,
        "constant_inflation": constant_inflation,
        "coverage_sign": coverage_sign,
        "fail_open": fail_open,
    }

    def se(age: float, coverage: float | None) -> float | None:
        return se_formula(0.2, age, coverage, **knobs)  # type: ignore[arg-type]

    bad: list[str] = []
    base = se(10.0, 1.0)
    older, sparser, fresh = se(60.0, 1.0), se(10.0, 0.5), se(0.0, 1.0)
    if base is None or older is None or sparser is None or fresh is None:
        return ["formula_unavailable_on_valid_inputs"]
    if older < base:
        bad.append("age_monotonicity")
    if sparser < base:
        bad.append("coverage_monotonicity")
    if abs(fresh - 0.2) > 1e-12:
        bad.append("fresh_complete_baseline")
    if se(10.0, None) is not None:
        bad.append("no_evidence_fail_closed")
    seasonal = se(400.0, 1.0)
    if seasonal is None or seasonal < base:
        bad.append("seasonal_recovery")
    # Supplementary, not one of the five preregistered invariants. Invariant 1 only
    # forbids a decrease, so a formula that ignores age entirely satisfies it -- which
    # is the very defect this work set out to find. A positive alpha must actually bite.
    if alpha > 0 and older <= base:
        bad.append("age_term_inert")
    return bad


def self_test_mutants() -> int:
    good: dict[str, float | bool] = {"alpha": 1e-4, "beta": 1e-3}
    if invariants(**good):  # type: ignore[arg-type]
        print("POSITIVE_INVARIANTS_FAILED", file=sys.stderr)
        return 1
    mutants: dict[str, dict[str, float | bool]] = {
        "negative_age_coefficient": {**good, "alpha": -1e-4},
        "inverted_coverage_sign": {**good, "coverage_sign": -1.0},
        "constant_inflation_at_baseline": {**good, "constant_inflation": 1e-3},
        "fail_open_without_denominator": {**good, "fail_open": True},
        "age_reset_on_season_switch": {**good, "reset_age": True},
    }
    survived = [
        name for name, kw in mutants.items() if not invariants(**kw)  # type: ignore[arg-type]
    ]
    if survived:
        print("MUTANTS_SURVIVED:" + ",".join(survived), file=sys.stderr)
        return 1
    print(json.dumps({"positive_invariants": "PASS", "mutants_rejected": len(mutants)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
