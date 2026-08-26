#!/usr/bin/env python3
"""Frozen-protocol runner for EV-SE v4. Emits evidence and verifies it.

Protocol: docs/review_packages/EV_SE_DRIFT_V4/PROTOCOL_FROZEN_V4_20260827.md
(commit 18f812b7).

The point estimates are unchanged from v3 -- protocol v4 corrects inference
semantics, not the estimator. What changes here:

  * two intervals per cell, each labelled with what it means, instead of one
    boundary critical value used everywhere and called a 95% CI;
  * a bootstrap clustered on teams rather than on team-seasons;
  * missingness asked as a point-in-time question, so it can return
    MISSINGNESS_NOT_IDENTIFIABLE rather than asserting a direction it cannot see;
  * calibration on production's cross-season latest-20 window with real coverage;
  * a pointer to the per-cell power artefact with its SHA-256, so no matrix row can
    claim work that does not exist.

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
import ev_se_v3_confound as C
import ev_se_v4_calibration as CAL
import ev_se_variogram as V
from _load import CORPUS_SHA256, CSV, load

HERE = os.path.dirname(__file__)
PACKAGE = os.path.join(HERE, "..", "docs", "review_packages", "EV_SE_DRIFT_V4")
EVIDENCE = os.path.join(PACKAGE, "EV_SE_DRIFT_V4_EVIDENCE.json")
POWER = os.path.join(PACKAGE, "EV_SE_DRIFT_V4_POWER.json")
IMPACT = os.path.join(PACKAGE, "EV_SE_DRIFT_V4_IMPACT.json")
DENOMINATOR = 20
ALPHA_LEVEL = 0.05

Series = list[tuple[float, float]]


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
        by_league: dict[str, list[tuple[str, str, Series]]] = {}
        for (league, team, season), series in load(comp).items():
            by_league.setdefault(league, []).append((team, season, sorted(series)))
        for league, entries in by_league.items():
            cell = f"{league}|{comp}"
            flat = [s for _t, _s, s in entries if len(s) >= 3]
            by_team: dict[str, list[Series]] = {}
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
            out[cell] = {
                "series": flat, "by_team": by_team, "pairs": within, "all_pairs": allp,
            }
    return out


def se0_squared_quantiles() -> dict[str, dict[str, float]]:
    buckets: dict[str, list[float]] = {}
    for comp in ("attack", "defence"):
        for (league, _team, _season), series in load(comp).items():
            s = sorted(series)
            for i in range(DENOMINATOR, len(s)):
                window = [y for _, y in s[i - DENOMINATOR : i]]
                mean = sum(window) / DENOMINATOR
                var = sum((v - mean) ** 2 for v in window) / (DENOMINATOR - 1)
                if var > 0:
                    buckets.setdefault(f"{league}|{comp}", []).append(var / DENOMINATOR)
    out: dict[str, dict[str, float]] = {}
    for cell, values in buckets.items():
        values.sort()
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
        b_lo, b_hi = M.profile_interval(
            series, sigma2, ll_full, critical=M.BOUNDARY_CRITICAL_95
        )
        p_lo, p_hi = M.profile_interval(
            series, sigma2, ll_full, critical=M.PROFILE_CRITICAL_95
        )
        boot_lo, boot_hi = M.cluster_bootstrap(cells[cell]["by_team"])

        stats = V.team_stats(pairs)
        v_intercept, v_slope = V.solve(stats, sorted(stats))
        v_lo, v_hi = V.bootstrap(stats)

        teams = {t for t, _, _ in pairs}
        span = max(d for _, d, _ in pairs) if pairs else 0.0
        gate = G.linearity_gate(pairs)
        supported = (
            len(teams) >= V.MIN_TEAMS and len(pairs) >= V.MIN_PAIRS
            and span >= V.MIN_DELTA_SPAN and gate["bins_sufficient"]
        )
        if not supported:
            status = "INSUFFICIENT_SUPPORT"
        elif gate["gate"] == "NONLINEAR_DRIFT":
            status = "NONLINEAR_DRIFT"
        elif pvalue < ALPHA_LEVEL:
            status = "DETECTED_UNCORRECTED"
        else:
            status = "NOT_DETECTED"
        report[cell] = {
            "teams": len(teams), "pairs": len(pairs), "series": len(series),
            "teams_bootstrapped": len(cells[cell]["by_team"]),
            "delta_span_days": _round(span, 3),
            "mle": {
                "sigma2_alpha_abs": _round(sigma2, 12),
                "tau2": _round(tau2),
                "optimum_at_boundary": sigma2 == 0.0,
                "loglik_full": _round(ll_full, 6),
                "loglik_null": _round(ll_null, 6),
                "lr_statistic": _round(2.0 * (ll_full - ll_null), 6),
                "p_value_boundary_mixture": _round(pvalue, 9),
                "boundary_region_95": {
                    "interval": [_round(b_lo, 12), _round(b_hi, 12)],
                    "critical_value": M.BOUNDARY_CRITICAL_95,
                    "meaning": (
                        "the set the one-sided boundary LRT does not reject at 5%; "
                        "excludes zero exactly when the test rejects; NOT a two-sided "
                        "95% confidence interval at an interior optimum"
                    ),
                },
                "profile_ci_95": {
                    "interval": [_round(p_lo, 12), _round(p_hi, 12)],
                    "critical_value": M.PROFILE_CRITICAL_95,
                    "meaning": (
                        "conventional two-sided 95% profile-likelihood interval; "
                        "correct at an interior optimum, conservative at the boundary"
                    ),
                },
                "cluster_bootstrap_200reps": {
                    "interval": [_round(boot_lo, 12), _round(boot_hi, 12)],
                    "resampling_unit": "team",
                    "meaning": (
                        "percentile interval from 200 replications clustered on teams; "
                        "a robustness check reported beside the likelihood intervals, "
                        "never the primary"
                    ),
                },
            },
            "variogram_comparator": {
                "alpha_abs": _round(v_slope, 12),
                "tau2": _round(v_intercept / 2 if v_intercept is not None else None),
                "bootstrap_ci": [_round(v_lo, 12), _round(v_hi, 12)],
            },
            "linearity_gate": {
                "delta2_ci_excludes_zero": gate["delta2_ci_excludes_zero"],
                "max_rel_dev_observed": _round(gate["max_rel_dev_observed"], 6),
                "max_rel_dev_quadratic": _round(gate["max_rel_dev_quadratic"], 6),
                "valid_bins": gate["valid_bins"],
                "gate": gate["gate"],
            },
            "status": status,
        }
    return report


def multiplicity(cells: dict[str, dict[str, Any]]) -> dict[str, Any]:
    entries = sorted(
        (float(v["mle"]["p_value_boundary_mixture"]), k) for k, v in cells.items()
    )
    m = len(entries)
    bonferroni = [k for p, k in entries if p <= ALPHA_LEVEL / m]
    largest = 0
    for i, (p, _k) in enumerate(entries, start=1):
        if p <= i / m * ALPHA_LEVEL:
            largest = i
    return {
        "tests": m,
        "family": "26 league x component cells, one one-sided test each",
        "uncorrected_rejections": [k for p, k in entries if p < ALPHA_LEVEL],
        "expected_false_positives_under_null": round(m * ALPHA_LEVEL, 3),
        "bonferroni_survivors": bonferroni,
        "bonferroni_meaning": "controls the family-wise error rate at 5% across all 26 tests",
        "benjamini_hochberg_survivors": [k for _p, k in entries[:largest]],
        "benjamini_hochberg_meaning": (
            "controls the false discovery rate at 5%; among the reported survivors an "
            "expected 5% are false, so a survivor is not individually certain"
        ),
        "sorted_p_values": [[k, _round(p, 9)] for p, k in entries],
    }


def form_mismatch(
    cells: dict[str, dict[str, Any]], se0: dict[str, dict[str, float]]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for cell, stats in sorted(se0.items()):
        alpha = cells[cell]["mle"]["sigma2_alpha_abs"]
        row: dict[str, Any] = {
            "se0_squared_p10": _round(stats["p10"]),
            "se0_squared_p50": _round(stats["p50"]),
            "se0_squared_p90": _round(stats["p90"]),
            "se0_squared_spread_p90_over_p10": _round(stats["p90"] / stats["p10"], 6),
            "states": stats["states"],
        }
        if alpha:
            row["alpha_rel_at_p10"] = _round(alpha / stats["p10"], 9)
            row["alpha_rel_at_p50"] = _round(alpha / stats["p50"], 9)
            row["alpha_rel_at_p90"] = _round(alpha / stats["p90"], 9)
        out[cell] = row
    return out


def path_c_verdict() -> dict[str, Any]:
    total = visible_early = 0
    earliest: str | None = None
    for line in open(CSV):
        p = line.rstrip("\n").split(",")
        if len(p) != 7 or p[0] in ("BEGIN", "ROLLBACK"):
            continue
        total += 1
        if earliest is None or p[3] < earliest:
            earliest = p[3]
        if p[3] < "2026-07":
            visible_early += 1
    return {
        "status": "PATH_C_NOT_IDENTIFIABLE",
        "rows_total": total,
        "rows_captured_before_2026_07": visible_early,
        "earliest_captured_at": earliest,
        "reason": (
            "the xG values did not exist in team_xg_match before 2026-07, so no "
            "evaluation epoch after the 2026-01-01 holdout boundary had any admissible "
            "history; a point-in-time replay correctly finds nothing because there was "
            "nothing to find"
        ),
        "write_semantics": {
            "ordinary_ingestion": (
                "upsert_team_xg_matches is first-write-wins behind an immutability "
                "guard: an existing row is compared field by field and any difference "
                "raises TEAM_XG_MATCH_IMMUTABLE_CONFLICT, otherwise the write is "
                "skipped. captured_at is never overwritten by ordinary ingestion"
            ),
            "controlled_exception": (
                "XgRetentionService.repair_derived_lineage can rewrite captured_at. It "
                "requires write_db=true plus a backup path, and _guarded_timestamp_updates "
                "raises XG_RETENTION_NON_TIMESTAMP_DRIFT if any non-timestamp field differs"
            ),
            "v3_description_was_wrong": (
                "v3 called this an upsert that overwrites captured_at and inferred the "
                "column was unreliable. It is close to a first-write record; the reason "
                "path C fails is missing history, not a corrupted column"
            ),
        },
        "production_path_is_pit_safe": (
            "ReadModelService._xg_uncertainty_rows drops rows with captured_at > as_of, "
            "so the shipped read model fails closed rather than reading the future"
        ),
        "what_would_make_it_identifiable": (
            "elapsed time. From the 2026-07 backfill onward captured_at accumulates a "
            "usable visibility history, so a holdout beginning after that date becomes "
            "answerable once enough of it exists. No retroactive record can recover the "
            "epochs where xG was simply absent"
        ),
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
    return {
        "xg_csv_sha256": digest.hexdigest(), "xg_csv_data_rows": rows,
        "xg_kickoff_min": lo, "xg_kickoff_max": hi,
    }


def build() -> dict[str, Any]:
    cells = series_by_cell()
    alpha_cells = estimate(cells)
    se0 = se0_squared_quantiles()
    return {
        "schema_version": "w2.ev_se.drift_v4.evidence.v1",
        "protocol_commit": "18f812b7",
        "history": {
            "v2": {"commit": "b34eada9", "note": "retained unmodified as failed history"},
            "v3": {
                "commit": "e429bd97",
                "note": (
                    "retained unmodified as failed history; its evidence reproduces at "
                    "that commit, not at HEAD, because v4 corrected shared modules"
                ),
            },
        },
        "inputs": {
            "corpus_sha256": CORPUS_SHA256, "holdout_cutoff": "2026-01-01",
            **xg_csv_fingerprint(),
        },
        "external_artefacts": {
            "power_per_cell": {
                "file": "EV_SE_DRIFT_V4_POWER.json", "sha256": _sha256_of(POWER),
                "present": os.path.exists(POWER),
            },
            "impact_and_representative_power": {
                "file": "EV_SE_DRIFT_V4_IMPACT.json", "sha256": _sha256_of(IMPACT),
                "present": os.path.exists(IMPACT),
            },
        },
        "alpha_cells": alpha_cells,
        "multiplicity": multiplicity(alpha_cells),
        "season_boundary": {c: G.boundary_model(cells[c]["all_pairs"]) for c in sorted(cells)},
        "missingness_beta_pit": B.kappa_by_league(pit=True),
        "missingness_beta_static_diagnostic": {
            "note": (
                "static xG existence, not point-in-time. Retained from v3 as a "
                "diagnostic; it does not answer the production question and its "
                "premise verdicts must not be quoted as if it did"
            ),
            "cells": B.kappa_by_league(),
        },
        "form_mismatch": form_mismatch(alpha_cells, se0),
        "calibration": CAL.report(),
        "confound_diagnostic": C.report(),
        "path_c": path_c_verdict(),
        "parameter_state": {
            "alpha_age_per_day": None,
            "beta_missing": None,
            "encoding_rule": (
                "NULL means no value was established. Zero is a claim that the effect "
                "is absent and is not available as a way to write NOT_IDENTIFIABLE. A "
                "consumer of an unset coefficient must omit the term rather than "
                "multiply by zero"
            ),
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
    if not paths:
        print("NO_NUMERIC_FIELDS_TO_MUTATE", file=sys.stderr)
        return 1
    step = max(1, len(paths) // 40)
    sampled = paths[::step]
    undetected: list[str] = []
    for trail in sampled:
        mutated = json.loads(text)
        node = mutated
        for key in trail[:-1]:
            node = node[key]
        node[trail[-1]] = node[trail[-1]] + 1e-6
        if render(mutated) == text:
            undetected.append(".".join(str(x) for x in trail))
    print(json.dumps({
        "numeric_fields": len(paths), "fields_mutated": len(sampled),
        "sampling": "deterministic paths[::step], not random",
        "mutations_undetected": undetected,
        "result": "PASS" if not undetected else "FAIL",
    }))
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
        print("EV_SE_DRIFT_V4_EVIDENCE_DIFF", file=sys.stderr)
        return 1
    print(json.dumps({"reproduction": "PASS"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
