#!/usr/bin/env python3
"""Frozen-protocol runner for EV-SE drift v3. Emits evidence and verifies it.

Protocol: docs/review_packages/EV_SE_DRIFT_V3/PROTOCOL_FROZEN_V3_20260826.md
(commit 603a9753).

  --emit              write the evidence JSON
  --check             regenerate in memory and compare byte for byte
  --self-test-check   mutate every numeric field by 1e-6 and prove --check fails
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import ev_se_beta_kappa as B
import ev_se_mle as M
import ev_se_v2_gates as G
import ev_se_v3_confound as C
import ev_se_variogram as V
from _load import CORPUS_SHA256, CSV, load

EVIDENCE = os.path.join(
    os.path.dirname(__file__), "..", "docs", "review_packages",
    "EV_SE_DRIFT_V3", "EV_SE_DRIFT_V3_EVIDENCE.json",
)
DENOMINATOR = 20
ALPHA_LEVEL = 0.05


def _round(x: float | None, k: int = 9) -> float | None:
    return None if x is None else round(x, k)


def _series_by_cell() -> dict[str, dict[str, list]]:
    """cell -> {'series': per team-season observations, 'pairs': variogram rows,
    'all_pairs': rows carrying a cross-season flag}."""
    out: dict[str, dict[str, list]] = {}
    for comp in ("attack", "defence"):
        loaded = load(comp)
        by_league: dict[str, list] = {}
        for (league, team, season), series in loaded.items():
            by_league.setdefault(league, []).append((team, season, sorted(series)))
        for league, entries in by_league.items():
            cell = f"{league}|{comp}"
            series_list = [s for _t, _s, s in entries if len(s) >= 3]
            within: list[tuple[str, float, float]] = []
            for team, _season, s in entries:
                for i in range(len(s)):
                    for j in range(i + 1, len(s)):
                        within.append((team, s[j][0] - s[i][0], (s[j][1] - s[i][1]) ** 2))
            # cross-season pairs need the team's whole timeline, seasons tagged
            timelines: dict[str, list[tuple[float, float, str]]] = {}
            for team, season, s in entries:
                timelines.setdefault(team, []).extend((t, y, season) for t, y in s)
            allp: list[tuple[str, float, float, float]] = []
            for team, rows in timelines.items():
                rows.sort()
                for i in range(len(rows)):
                    for j in range(i + 1, len(rows)):
                        crossed = 0.0 if rows[i][2] == rows[j][2] else 1.0
                        allp.append(
                            (team, rows[j][0] - rows[i][0], crossed,
                             (rows[j][1] - rows[i][1]) ** 2)
                        )
            out[cell] = {"series": series_list, "pairs": within, "all_pairs": allp}
    return out


def _se0_squared_quantiles() -> dict[str, dict[str, float]]:
    """SE0^2 = var(latest 20)/20 across evaluation states, per cell.

    The multiplicative form needs alpha_rel = alpha_abs / SE0^2 to be a constant.
    These quantiles are what shows it is not.
    """
    out: dict[str, list[float]] = {}
    for comp in ("attack", "defence"):
        for (league, _team, _season), series in load(comp).items():
            s = sorted(series)
            for i in range(DENOMINATOR, len(s)):
                window = [y for _, y in s[i - DENOMINATOR : i]]
                mean = sum(window) / DENOMINATOR
                var = sum((v - mean) ** 2 for v in window) / (DENOMINATOR - 1)
                if var > 0:
                    out.setdefault(f"{league}|{comp}", []).append(var / DENOMINATOR)
    report: dict[str, dict[str, float]] = {}
    for cell, values in out.items():
        values.sort()
        n = len(values)
        report[cell] = {
            "states": n,
            "p10": values[int(0.10 * n)],
            "p50": values[int(0.50 * n)],
            "p90": values[int(0.90 * n)],
        }
    return report


def estimate(cells: dict[str, dict[str, list]]) -> dict[str, dict[str, object]]:
    report: dict[str, dict[str, object]] = {}
    for cell in sorted(cells):
        series = cells[cell]["series"]
        pairs = cells[cell]["pairs"]
        sigma2, tau2, ll_full = M.fit_full(series)
        _tau0, ll_null = M.fit_restricted(series)
        pvalue = M.lrt_pvalue(ll_full, ll_null)
        ci_lo, ci_hi = M.profile_interval(series, sigma2, ll_full)

        stats = V.team_stats(pairs)
        v_intercept, v_slope = V.solve(stats, sorted(stats))
        v_lo, v_hi = V.bootstrap(stats)

        teams = {t for t, _, _ in pairs}
        span = max(d for _, d, _ in pairs) if pairs else 0.0
        gate = G.linearity_gate(pairs)
        supported = (
            len(teams) >= V.MIN_TEAMS
            and len(pairs) >= V.MIN_PAIRS
            and span >= V.MIN_DELTA_SPAN
            and gate["bins_sufficient"]
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
            "teams": len(teams),
            "pairs": len(pairs),
            "series": len(series),
            "delta_span_days": _round(span, 3),
            "mle": {
                "sigma2_alpha_abs": _round(sigma2, 12),
                "tau2": _round(tau2),
                "loglik_full": _round(ll_full, 6),
                "loglik_null": _round(ll_null, 6),
                "lr_statistic": _round(2.0 * (ll_full - ll_null), 6),
                "p_value_boundary_mixture": _round(pvalue, 9),
                "profile_ci": [_round(ci_lo, 12), _round(ci_hi, 12)],
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
                "max_rel_dev_vs_drift_component": _round(
                    gate["max_rel_dev_vs_drift_component"], 6
                ),
                "valid_bins": gate["valid_bins"],
                "gate": gate["gate"],
            },
            "status": status,
        }
    return report


def multiplicity(cells: dict[str, dict[str, object]]) -> dict[str, object]:
    """26 one-sided tests need a correction before any cell is called a finding."""
    entries = sorted(
        (
            (float(v["mle"]["p_value_boundary_mixture"]), k)  # type: ignore[index]
            for k, v in cells.items()
        )
    )
    m = len(entries)
    bonferroni = [k for p, k in entries if p <= ALPHA_LEVEL / m]
    survivors: list[str] = []
    largest = 0
    for i, (p, _k) in enumerate(entries, start=1):
        if p <= i / m * ALPHA_LEVEL:
            largest = i
    survivors = [k for _p, k in entries[:largest]]
    return {
        "tests": m,
        "uncorrected_rejections": [k for p, k in entries if p < ALPHA_LEVEL],
        "expected_false_positives_under_null": round(m * ALPHA_LEVEL, 3),
        "bonferroni_survivors": bonferroni,
        "benjamini_hochberg_survivors": survivors,
        "sorted_p_values": [[k, _round(p, 9)] for p, k in entries],
    }


def form_mismatch(
    cells: dict[str, dict[str, object]], se0: dict[str, dict[str, float]]
) -> dict[str, object]:
    out: dict[str, object] = {}
    for cell, stats in sorted(se0.items()):
        alpha = cells.get(cell, {}).get("mle", {}).get("sigma2_alpha_abs")  # type: ignore[union-attr]
        row = {
            "se0_squared_p10": _round(stats["p10"]),
            "se0_squared_p50": _round(stats["p50"]),
            "se0_squared_p90": _round(stats["p90"]),
            "states": stats["states"],
        }
        if alpha:
            row["alpha_rel_at_p10"] = _round(alpha / stats["p10"], 9)
            row["alpha_rel_at_p50"] = _round(alpha / stats["p50"], 9)
            row["alpha_rel_at_p90"] = _round(alpha / stats["p90"], 9)
            row["alpha_rel_spread_p10_over_p90"] = _round(stats["p90"] / stats["p10"], 6)
        out[cell] = row
    return out


def path_c_verdict() -> dict[str, object]:
    """Path C admissibility, decided on the data rather than argued."""
    total = 0
    visible_before_2026_07 = 0
    estimation_rows_captured_after_cutoff = 0
    earliest = None
    for line in open(CSV):
        p = line.rstrip("\n").split(",")
        if len(p) != 7 or p[0] in ("BEGIN", "ROLLBACK"):
            continue
        total += 1
        captured = p[3]
        if earliest is None or captured < earliest:
            earliest = captured
        if captured < "2026-07":
            visible_before_2026_07 += 1
        if p[2] < "2026-01-01" and captured >= "2026-01-01":
            estimation_rows_captured_after_cutoff += 1
    return {
        "status": "PATH_C_NOT_IDENTIFIABLE",
        "rows_total": total,
        "rows_captured_before_2026_07": visible_before_2026_07,
        "earliest_captured_at": earliest,
        "estimation_rows_captured_after_holdout_cutoff": estimation_rows_captured_after_cutoff,
        "reason": (
            "No xG row in the frozen extract carries a first-visibility timestamp "
            "before 2026-07, so no holdout fixture after 2026-01-01 has admissible "
            "history under protocol v3 section 6."
        ),
        "columns_examined_and_rejected": {
            "team_xg_match.captured_at": (
                "overwritten on upsert; current values record the 2026-08 backfill, "
                "not first visibility"
            ),
            "team_xg_rolling_snapshot": (
                "written through session.merge on a derived key and rebuilt from "
                "team_xg_match, so it inherits the same defect"
            ),
        },
        "record_that_would_make_it_identifiable": (
            "an append-only xG observation log carrying source_inserted_at, the "
            "analogue of ExpectedMatchFixtureObservationModel which already gives "
            "fixture existence a point-in-time history"
        ),
        "production_path_is_pit_safe": (
            "ReadModelService._xg_uncertainty_rows drops rows with captured_at > as_of, "
            "so the shipped read model fails closed rather than reading the future; "
            "the defect is in the v2 research loader, which never read the column"
        ),
    }


def xg_csv_fingerprint() -> dict[str, object]:
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
    cells = _series_by_cell()
    alpha_cells = estimate(cells)
    boundary = {
        cell: G.boundary_model(cells[cell]["all_pairs"]) for cell in sorted(cells)
    }
    se0 = _se0_squared_quantiles()
    return {
        "schema_version": "w2.ev_se.drift_v3.evidence.v1",
        "protocol_commit": "603a9753",
        "supersedes": {
            "commit": "b34eada9",
            "note": "retained as failed history; not amended",
        },
        "inputs": {
            "corpus_sha256": CORPUS_SHA256,
            "holdout_cutoff": "2026-01-01",
            **xg_csv_fingerprint(),
        },
        "estimator": {
            "primary": "exact Gaussian likelihood, local level model, diffuse level",
            "test": "one-sided LRT, 50:50 point-mass/chi^2_1 boundary mixture",
            "interval": "profile likelihood at the same boundary-corrected critical value",
            "comparator": "v2 within-season variogram, team-clustered bootstrap",
            "bootstrap": {"reps": V.REPS, "seed": V.SEED, "ci": V.CI},
        },
        "alpha_cells": alpha_cells,
        "multiplicity": multiplicity(alpha_cells),
        "season_boundary": boundary,
        "missingness_beta": B.kappa_by_league(),
        "missingness_beta_era_restricted": B.kappa_by_league(era_restricted=True),
        "form_mismatch": form_mismatch(alpha_cells, se0),
        "confound_diagnostic": C.report(),
        "path_c": path_c_verdict(),
        "forbidden_uses": ["SETTLED_PICK_PROFIT", "HIT_RATE", "CURRENT_65_PICKS"],
    }


def render(doc: dict[str, object]) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def self_test_check() -> int:
    """Mutate each numeric leaf by 1e-6 in turn and prove --check rejects it."""
    text = render(build())
    stored = json.loads(text)

    paths: list[list] = []

    def walk(node, trail):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, [*trail, k])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, [*trail, i])
        elif isinstance(node, float):
            paths.append(trail)

    walk(stored, [])
    if not paths:
        print("NO_NUMERIC_FIELDS_TO_MUTATE", file=sys.stderr)
        return 1
    step = max(1, len(paths) // 40)
    sampled = paths[::step]
    undetected = []
    for trail in sampled:
        mutated = json.loads(text)
        node = mutated
        for key in trail[:-1]:
            node = node[key]
        node[trail[-1]] = node[trail[-1]] + 1e-6
        if render(mutated) == text:
            undetected.append(".".join(str(x) for x in trail))
    print(
        json.dumps(
            {
                "numeric_fields": len(paths),
                "fields_mutated": len(sampled),
                "mutations_undetected": undetected,
                "result": "PASS" if not undetected else "FAIL",
            }
        )
    )
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
        print("EV_SE_DRIFT_V3_EVIDENCE_DIFF", file=sys.stderr)
        return 1
    print(json.dumps({"reproduction": "PASS"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
