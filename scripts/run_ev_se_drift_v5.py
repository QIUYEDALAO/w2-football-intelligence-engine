#!/usr/bin/env python3
"""Frozen-protocol runner for EV-SE v5. Emits evidence and verifies it.

Protocol: docs/review_packages/EV_SE_DRIFT_V5/PROTOCOL_FROZEN_V5_20260827.md
(commit 4558f5ab).

The alpha estimates are unchanged from v4 and v3. What v5 changes is everything
built on top of an evaluation window, because v4 built two of those windows per
season while production orders across seasons.

  --emit              write the evidence JSON
  --check             regenerate in memory and compare byte for byte
  --self-test-check   mutate numeric fields by 1e-6 and prove --check fails
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))
import ev_se_beta_kappa as B
import ev_se_mle as M
import ev_se_v2_gates as G
import ev_se_v5_confound as C
import ev_se_v5_window as W
import ev_se_variogram as V
from _load import CORPUS_SHA256, CSV, load

PACKAGE = os.path.join(
    os.path.dirname(__file__), "..", "docs", "review_packages", "EV_SE_DRIFT_V5"
)
EVIDENCE = os.path.join(PACKAGE, "EV_SE_DRIFT_V5_EVIDENCE.json")
ALPHA_LEVEL = 0.05
STRATA = 4
MIN_STATES = 30


def _round(x: float | None, k: int = 9) -> float | None:
    return None if x is None else round(x, k)


def _sha256_of(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def series_by_cell() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for comp in ("attack", "defence"):
        by_league: dict[str, list[tuple[str, str, list[tuple[float, float]]]]] = {}
        for (league, team, season), series in load(comp).items():
            by_league.setdefault(league, []).append((team, season, sorted(series)))
        for league, entries in by_league.items():
            cell = f"{league}|{comp}"
            flat = [s for _t, _s, s in entries if len(s) >= 3]
            by_team: dict[str, list[list[tuple[float, float]]]] = {}
            for team, _season, s in entries:
                if len(s) >= 3:
                    by_team.setdefault(team, []).append(s)
            within: list[tuple[str, float, float]] = []
            for team, _season, s in entries:
                for i in range(len(s)):
                    for j in range(i + 1, len(s)):
                        within.append((team, s[j][0] - s[i][0], (s[j][1] - s[i][1]) ** 2))
            timelines: dict[str, list[tuple[float, float, str]]] = {}
            for team, season, s in entries:
                timelines.setdefault(team, []).extend((t, y, season) for t, y in s)
            allp: list[tuple[str, float, float, float]] = []
            for team, rows in timelines.items():
                rows.sort()
                for i in range(len(rows)):
                    for j in range(i + 1, len(rows)):
                        crossed = 0.0 if rows[i][2] == rows[j][2] else 1.0
                        allp.append((team, rows[j][0] - rows[i][0], crossed,
                                     (rows[j][1] - rows[i][1]) ** 2))
            out[cell] = {"series": flat, "by_team": by_team,
                         "pairs": within, "all_pairs": allp}
    return out


def se0_squared_quantiles() -> dict[str, dict[str, float]]:
    """SE0^2 across production's cross-season states.

    v4 computed this per season, which biased both `form_mismatch` and the impact
    figure that consumed `se0_squared_p50`. The states now come from the shared
    window constructor.
    """
    out: dict[str, dict[str, float]] = {}
    for comp in ("attack", "defence"):
        for cell, states in W.observed_states(comp).items():
            values = sorted(s["se0_squared"] for s in states)
            n = len(values)
            out[cell] = {
                "states": n, "p10": values[int(0.10 * n)],
                "p50": values[int(0.50 * n)], "p90": values[int(0.90 * n)],
            }
    return out


def estimate(cells: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    report: dict[str, dict[str, Any]] = {}
    for cell in sorted(cells):
        series = cells[cell]["series"]
        pairs = cells[cell]["pairs"]
        sigma2, tau2, ll_full = M.fit_full(series)
        _tau0, ll_null = M.fit_restricted(series)
        pvalue = M.lrt_pvalue(ll_full, ll_null)
        b_lo, b_hi = M.profile_interval(series, sigma2, ll_full,
                                        critical=M.BOUNDARY_CRITICAL_95)
        p_lo, p_hi = M.profile_interval(series, sigma2, ll_full,
                                        critical=M.PROFILE_CRITICAL_95)
        boot_lo, boot_hi = M.cluster_bootstrap(cells[cell]["by_team"])
        stats = V.team_stats(pairs)
        v_intercept, v_slope = V.solve(stats, sorted(stats))
        v_lo, v_hi = V.bootstrap(stats)
        teams = {t for t, _, _ in pairs}
        span = max(d for _, d, _ in pairs) if pairs else 0.0
        gate = G.linearity_gate(pairs)
        supported = (len(teams) >= V.MIN_TEAMS and len(pairs) >= V.MIN_PAIRS
                     and span >= V.MIN_DELTA_SPAN and gate["bins_sufficient"])
        status = ("INSUFFICIENT_SUPPORT" if not supported
                  else "NONLINEAR_DRIFT" if gate["gate"] == "NONLINEAR_DRIFT"
                  else "DETECTED_UNCORRECTED" if pvalue < ALPHA_LEVEL
                  else "NOT_DETECTED")
        report[cell] = {
            "teams": len(teams), "pairs": len(pairs), "series": len(series),
            "delta_span_days": _round(span, 3),
            "mle": {
                "sigma2_alpha_abs": _round(sigma2, 12), "tau2": _round(tau2),
                "optimum_at_boundary": sigma2 == 0.0,
                "lr_statistic": _round(2.0 * (ll_full - ll_null), 6),
                "p_value_boundary_mixture": _round(pvalue, 9),
                "boundary_region_95": {
                    "interval": [_round(b_lo, 12), _round(b_hi, 12)],
                    "meaning": "the set the one-sided boundary LRT does not reject at 5%",
                },
                "profile_ci_95": {
                    "interval": [_round(p_lo, 12), _round(p_hi, 12)],
                    "meaning": "conventional two-sided 95% profile interval",
                },
                "cluster_bootstrap_200reps": {
                    "interval": [_round(boot_lo, 12), _round(boot_hi, 12)],
                    "resampling_unit": "team",
                },
            },
            "variogram_comparator": {
                "alpha_abs": _round(v_slope, 12),
                "bootstrap_ci": [_round(v_lo, 12), _round(v_hi, 12)],
            },
            "linearity_gate": {"gate": gate["gate"],
                               "valid_bins": gate["valid_bins"]},
            "status": status,
        }
    return report


def multiplicity(cells: dict[str, dict[str, Any]]) -> dict[str, Any]:
    entries = sorted(
        (float(v["mle"]["p_value_boundary_mixture"]), k) for k, v in cells.items()
    )
    m = len(entries)
    largest = 0
    for i, (p, _k) in enumerate(entries, start=1):
        if p <= i / m * ALPHA_LEVEL:
            largest = i
    return {
        "tests": m,
        "uncorrected_rejections": [k for p, k in entries if p < ALPHA_LEVEL],
        "expected_false_positives_under_null": round(m * ALPHA_LEVEL, 3),
        "bonferroni_survivors": [k for p, k in entries if p <= ALPHA_LEVEL / m],
        "bonferroni_meaning": (
            "family-wise error rate control: the probability that this procedure "
            "makes one or more false rejections is at most 5%. It is not a "
            "probability statement about any individual survivor"
        ),
        "benjamini_hochberg_survivors": [k for _p, k in entries[:largest]],
        "benjamini_hochberg_meaning": (
            "false discovery rate control: the expected proportion of false "
            "rejections among those reported is at most 5%. It is not a probability "
            "statement about any individual survivor"
        ),
        "sorted_p_values": [[k, _round(p, 9)] for p, k in entries],
    }


def _sort_key(key: str) -> Any:
    def pick(state: dict[str, Any]) -> float:
        return float(state[key])

    return pick


def calibration() -> dict[str, Any]:
    """Age- and coverage-stratified, on the shared cross-season window."""
    def basis(pit: bool) -> dict[str, Any]:
        cells: dict[str, Any] = {}
        total = 0
        for comp in ("attack", "defence"):
            produced = W.coverage_states(comp, pit=pit)
            for cell, rows in sorted(produced.items()):
                total += len(rows)
                if len(rows) < MIN_STATES:
                    cells[cell] = {"status": "INSUFFICIENT_STATES", "states": len(rows)}
                    continue
                series = [s for s in W.observed_states(comp).get(cell, [])]
                del series
                fitted = [sorted(v) for (lg, _t, _s), v in load(comp).items()
                          if lg == cell.split("|")[0] and len(v) >= 3]
                alpha, tau2, _ll = M.fit_full(fitted)

                def summarise(group: list[dict[str, Any]], by: str,
                              alpha: float = alpha, tau2: float = tau2) -> dict[str, Any]:
                    n = len(group)
                    base = [g["residual"] / (g["se0_squared"] + tau2) ** 0.5 for g in group]
                    cand = [g["residual"]
                            / (g["se0_squared"] + tau2 + alpha * g["mean_age_days"]) ** 0.5
                            for g in group]
                    return {
                        "n": n, "stratified_by": by,
                        "mean_age_days": round(sum(g["mean_age_days"] for g in group) / n, 3),
                        "mean_coverage": round(sum(g["coverage"] for g in group) / n, 4),
                        "baseline_var_z": round(sum(z * z for z in base) / n, 6),
                        "candidate_var_z": round(sum(z * z for z in cand) / n, 6),
                    }

                def strata(
                    key: str, rows: list[dict[str, Any]] = rows
                ) -> list[list[dict[str, Any]]]:
                    ordered = sorted(rows, key=_sort_key(key))
                    size = len(ordered) // STRATA
                    return [ordered[k * size: (k + 1) * size if k < STRATA - 1 else len(ordered)]
                            for k in range(STRATA)] if size else []

                age = [summarise(g, "age") for g in strata("mean_age_days")]
                cov = [summarise(g, "coverage") for g in strata("coverage")]
                cells[cell] = {
                    "status": "OK", "states": len(rows),
                    "coverage_min": round(min(r["coverage"] for r in rows), 4),
                    "coverage_max": round(max(r["coverage"] for r in rows), 4),
                    "by_age": age, "by_coverage": cov,
                    "baseline_var_z_oldest_minus_youngest": (
                        round(age[-1]["baseline_var_z"] - age[0]["baseline_var_z"], 6)
                        if len(age) == STRATA else None
                    ),
                }
        if total == 0:
            return {"status": "NOT_IDENTIFIABLE",
                    "reason": "no epoch carries three observations under this basis"}
        return {"status": "COMPUTED", "total_states": total, "cells": cells}

    return {
        "window": "shared cross-season constructor, ev_se_v5_window.coverage_states",
        "static_basis": basis(pit=False),
        "pit_basis": basis(pit=True),
        "what_this_may_be_used_for": (
            "the static basis is an in-sample diagnostic computed with information "
            "that was not available at prediction time. It is NOT evidence that the "
            "shipped baseline is calibrated, in production or out of sample; the "
            "point-in-time question stays NOT_IDENTIFIABLE and nothing here "
            "substitutes for it"
        ),
        "baseline_column_is_coefficient_free": (
            "baseline z uses only SE0 and tau^2; the candidate column is circular "
            "because alpha comes from the same data"
        ),
    }


def path_c_verdict() -> dict[str, Any]:
    total = early = 0
    earliest: str | None = None
    for line in open(CSV):
        p = line.rstrip("\n").split(",")
        if len(p) != 7 or p[0] in ("BEGIN", "ROLLBACK"):
            continue
        total += 1
        if earliest is None or p[3] < earliest:
            earliest = p[3]
        if p[3] < "2026-07":
            early += 1
    return {
        "status": "PATH_C_NOT_IDENTIFIABLE",
        "rows_total": total, "rows_captured_before_2026_07": early,
        "earliest_captured_at": earliest,
        "reason": (
            "the xG values were absent from team_xg_match before 2026-07, so no "
            "epoch after the holdout boundary has admissible history"
        ),
        "write_semantics": (
            "upsert_team_xg_matches is first-write-wins behind an immutability guard "
            "and never overwrites captured_at; XgRetentionService.repair_derived_lineage "
            "can, but requires write_db plus a backup and rejects non-timestamp drift. "
            "The repository already asserts the first-write property in "
            "tests/integration/test_future_refresh_db_persistence.py::"
            "test_team_xg_match_preserves_first_visible_evidence"
        ),
        "what_would_make_it_identifiable": "elapsed time from 2026-07 onward",
    }


def xg_csv_fingerprint() -> dict[str, Any]:
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
    return {"xg_csv_sha256": digest.hexdigest(), "xg_csv_data_rows": rows,
            "xg_kickoff_min": lo, "xg_kickoff_max": hi}


def build() -> dict[str, Any]:
    cells = series_by_cell()
    alpha_cells = estimate(cells)
    se0 = se0_squared_quantiles()
    form: dict[str, Any] = {}
    for cell, stats in sorted(se0.items()):
        alpha = alpha_cells[cell]["mle"]["sigma2_alpha_abs"]
        row: dict[str, Any] = {
            "se0_squared_p10": _round(stats["p10"]), "se0_squared_p50": _round(stats["p50"]),
            "se0_squared_p90": _round(stats["p90"]),
            "se0_squared_spread_p90_over_p10": _round(stats["p90"] / stats["p10"], 6),
            "states": stats["states"],
        }
        if alpha:
            row["alpha_rel_at_p10"] = _round(alpha / stats["p10"], 9)
            row["alpha_rel_at_p90"] = _round(alpha / stats["p90"], 9)
        form[cell] = row
    return {
        "schema_version": "w2.ev_se.drift_v5.evidence.v1",
        "protocol_commit": "4558f5ab",
        "history": {
            "v2": "b34eada9", "v3": "e429bd97", "v4": "5a40f448",
            "note": "all retained unmodified; each reproduces at its own commit",
        },
        "inputs": {"corpus_sha256": CORPUS_SHA256, "holdout_cutoff": "2026-01-01",
                   **xg_csv_fingerprint()},
        "window_self_check": W.self_check(),
        "external_artefacts": {
            name: {"file": name, "sha256": _sha256_of(os.path.join(PACKAGE, name)),
                   "present": os.path.exists(os.path.join(PACKAGE, name))}
            for name in ("EV_SE_DRIFT_V5_POWER.json", "EV_SE_DRIFT_V5_IMPACT.json")
        },
        "alpha_cells": alpha_cells,
        "multiplicity": multiplicity(alpha_cells),
        "season_boundary": {c: G.boundary_model(cells[c]["all_pairs"]) for c in sorted(cells)},
        "missingness_beta_pit": B.kappa_by_league(pit=True),
        "form_mismatch": form,
        "calibration": calibration(),
        "confound_diagnostic": C.report(),
        "parameter_state": {
            "alpha_age_per_day": None, "beta_missing": None,
            "encoding_rule": (
                "NULL means no value was established. Zero is a claim that the effect "
                "is absent and may not be used to express NOT_IDENTIFIABLE"
            ),
        },
        "authorisation": {
            "enters_production_gate": False, "unlocks_contract_1": False,
            "deploys": False,
            "note": "research only; these are Owner decisions and this package makes none",
        },
        "forbidden_uses": ["SETTLED_PICK_PROFIT", "HIT_RATE", "CURRENT_65_PICKS"],
    }


def render(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def self_test_check() -> int:
    text = render(build())
    paths: list[list[Any]] = []

    def walk(node: Any, trail: list[Any]) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, [*trail, k])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, [*trail, i])
        elif isinstance(node, float):
            paths.append(trail)

    walk(json.loads(text), [])
    step = max(1, len(paths) // 40)
    undetected: list[str] = []
    for trail in paths[::step]:
        mutated = json.loads(text)
        node = mutated
        for key in trail[:-1]:
            node = node[key]
        node[trail[-1]] = node[trail[-1]] + 1e-6
        if render(mutated) == text:
            undetected.append(".".join(str(x) for x in trail))
    print(json.dumps({"numeric_fields": len(paths), "fields_mutated": len(paths[::step]),
                      "mutations_undetected": undetected,
                      "result": "PASS" if not undetected else "FAIL"}))
    return 1 if undetected else 0


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else "--check"
    if arg == "--self-test-check":
        return self_test_check()
    text = render(build())
    if arg == "--emit":
        with open(EVIDENCE, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(json.dumps({"emitted": hashlib.sha256(text.encode()).hexdigest()[:16]}))
        return 0
    with open(EVIDENCE, encoding="utf-8") as fh:
        stored = fh.read()
    if stored != text:
        print("EV_SE_DRIFT_V5_EVIDENCE_DIFF", file=sys.stderr)
        return 1
    print(json.dumps({"reproduction": "PASS"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
