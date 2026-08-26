#!/usr/bin/env python3
"""Age- and coverage-stratified calibration of the baseline and candidate formulas.

Protocol v3 section 11 (commit 603a9753).

IN-SAMPLE. Path C is not identifiable, so this runs inside the estimation period
and is not a holdout. It is labelled that way everywhere it appears. The candidate
uses an alpha estimated from this same data, so the candidate's own numbers are
circular and are reported only for completeness.

The part that is *not* circular, and is the point of this file, is the baseline
column. It needs no estimated coefficient at all:

    z = (y_next - mean(window)) / sqrt(SE0^2 + tau^2)

If staleness matters, z's variance rises with the age of the window. If it does
not, the whole age term is answering a question the data never asked. That trend
is a fact about prediction error, not a property of any fitted model.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from typing import Any

import ev_se_mle as M
from _load import load
from ev_se_beta_kappa import DENOMINATOR

STRATA = 4


def states_for(component: str) -> dict[str, list[Any]]:
    """(cell, team, mean_age, coverage, z_numerator, se0_squared) per evaluation state."""
    out: dict[str, list[Any]] = {}
    for (league, team, _season), series in load(component).items():
        s = sorted(series)
        if len(s) <= DENOMINATOR:
            continue
        for i in range(DENOMINATOR, len(s)):
            as_of, actual = s[i]
            window = s[i - DENOMINATOR : i]
            values = [y for _, y in window]
            n = len(values)
            mean = sum(values) / n
            var = sum((v - mean) ** 2 for v in values) / (n - 1)
            if var <= 0:
                continue
            mean_age = sum(as_of - t for t, _ in window) / n
            out.setdefault(f"{league}|{component}", []).append(
                (team, mean_age, n / DENOMINATOR, actual - mean, var / n)
            )
    return out


def _quantile_strata(rows: list[Any], index: int) -> list[list[Any]]:
    ordered = sorted(rows, key=lambda r: r[index])
    size = len(ordered) // STRATA
    if size == 0:
        return []
    return [
        ordered[k * size : (k + 1) * size if k < STRATA - 1 else len(ordered)]
        for k in range(STRATA)
    ]


def report() -> dict[str, object]:
    out: dict[str, Any] = {}
    for component in ("attack", "defence"):
        cells = states_for(component)
        for cell, rows in sorted(cells.items()):
            series = [
                sorted(s)
                for (lg, _t, _s), s in load(component).items()
                if lg == cell.split("|")[0] and len(s) >= 3
            ]
            alpha, tau2, _ll = M.fit_full(series)

            def summarise(
                group: list[Any], by: str, *, alpha: float = alpha, tau2: float = tau2
            ) -> dict[str, Any]:
                zs_base, zs_cand = [], []
                for _team, age, _cov, resid, se0sq in group:
                    zs_base.append(resid / (se0sq + tau2) ** 0.5)
                    zs_cand.append(resid / (se0sq + tau2 + alpha * age) ** 0.5)
                n = len(group)
                return {
                    "n": n,
                    "mean_age_days": round(sum(g[1] for g in group) / n, 3),
                    "mean_coverage": round(sum(g[2] for g in group) / n, 4),
                    "baseline_var_z": round(sum(z * z for z in zs_base) / n, 6),
                    "candidate_var_z": round(sum(z * z for z in zs_cand) / n, 6),
                    "stratified_by": by,
                }

            age_strata = [summarise(g, "age") for g in _quantile_strata(rows, 1)]
            cov_strata = [summarise(g, "coverage") for g in _quantile_strata(rows, 2)]
            trend = None
            if len(age_strata) == STRATA:
                trend = round(
                    age_strata[-1]["baseline_var_z"] - age_strata[0]["baseline_var_z"], 6
                )
            out[cell] = {
                "alpha_used": alpha,
                "tau2_used": tau2,
                "by_age": age_strata,
                "by_coverage": cov_strata,
                "baseline_var_z_oldest_minus_youngest": trend,
            }
    return {
        "basis": "IN_SAMPLE_ESTIMATION_PERIOD",
        "not_a_holdout": (
            "path C is not identifiable, so no out-of-sample calibration exists; "
            "the candidate column is circular because alpha comes from this data"
        ),
        "baseline_column_is_coefficient_free": (
            "baseline z uses only SE0 and tau^2, so its trend across age strata is a "
            "fact about prediction error rather than a property of any fitted model"
        ),
        "cells": out,
    }


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, sort_keys=True))
