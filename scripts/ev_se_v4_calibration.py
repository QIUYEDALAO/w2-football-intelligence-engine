#!/usr/bin/env python3
"""Age- and coverage-stratified calibration on production's own window semantics.

Protocol v4 section 6 (commit 18f812b7).

v3's calibration measured neither thing it named. It grouped history by
`(league, team, season)`, so the window reset at every season boundary, while
production takes the latest 20 by kickoff across seasons. And it drew the window
from the xG-only series, so `|O| = |E| = 20` always and coverage was identically
1.0 in every stratum. Nothing was stratified by coverage at all.

Here the window is the latest 20 **expected** fixtures from the frozen corpus,
across seasons, matching how `team_xg_matches_for_teams` orders rows with
`limit_per_team=20`. Coverage is `|O|/|E|` and varies. Two bases are computed and
never mixed:

  static  -- `O` is decided by final xG existence. A diagnostic. It overstates what
             was knowable at the evaluation epoch.
  pit     -- `O` is decided by `captured_at <= as_of`, the filter
             `ReadModelService._xg_uncertainty_rows` applies. This is the
             production question, and it reports NOT_IDENTIFIABLE rather than
             falling back to `static`.

The baseline column uses only `SE0` and `tau^2`, so it stays free of any fitted
coefficient. The candidate column is circular whenever alpha comes from this same
data, and says so.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import ev_se_mle as M
from _load import CORPUS, CSV, LEAGUE
from ev_se_beta_kappa import DENOMINATOR, MIN_OBSERVED, observed_capture_times
from ev_se_drift_alpha import HOLDOUT_CUTOFF, parse_ts

STRATA = 4
MIN_STATES = 30


def _xg_values(component: str) -> dict[tuple[str, str], float]:
    column = 4 if component == "attack" else 5
    out: dict[tuple[str, str], float] = {}
    for line in open(CSV):
        parts = line.rstrip("\n").split(",")
        if len(parts) != 7 or parts[0] in ("BEGIN", "ROLLBACK"):
            continue
        try:
            out[(parts[0], parts[1])] = float(parts[column])
        except ValueError:
            continue
    return out


def _expected_timelines() -> dict[tuple[str, str], list[tuple[float, str]]]:
    """(league, team) -> [(kickoff_epoch_days, fixture_id)] across seasons, sorted."""
    out: dict[tuple[str, str], list[tuple[float, str]]] = {}
    for row in json.load(open(CORPUS))["history_rows"]:
        league = LEAGUE.get(row["provider_league_id"])
        if league is None or row["kickoff_utc"] >= HOLDOUT_CUTOFF:
            continue
        out.setdefault((league, row["team_id"]), []).append(
            (parse_ts(row["kickoff_utc"]), row["provider_fixture_id"])
        )
    for series in out.values():
        series.sort()
    return out


def states(component: str, *, pit: bool) -> dict[str, list[tuple[float, float, float, float]]]:
    """cell -> [(mean_age, coverage, residual, se0_squared), ...]."""
    capture = observed_capture_times()
    values = _xg_values(component)
    timelines = _expected_timelines()
    out: dict[str, list[tuple[float, float, float, float]]] = {}
    for (league, team), timeline in timelines.items():
        for i in range(DENOMINATOR, len(timeline)):
            as_of, target_fixture = timeline[i]
            actual = values.get((target_fixture, team))
            if actual is None:
                continue                       # no realised value to score against
            expected = timeline[i - DENOMINATOR : i]
            observed: list[tuple[float, float]] = []
            for kickoff, fixture in expected:
                seen = capture.get((fixture, team))
                if seen is None:
                    continue
                if pit and seen > as_of:
                    continue                   # not visible yet at this epoch
                value = values.get((fixture, team))
                if value is not None:
                    observed.append((kickoff, value))
            if len(observed) < MIN_OBSERVED:
                continue                       # production fails closed here
            sample = [v for _, v in observed]
            n = len(sample)
            mean = sum(sample) / n
            variance = sum((v - mean) ** 2 for v in sample) / (n - 1)
            if variance <= 0:
                continue
            mean_age = sum(as_of - k for k, _ in observed) / n
            out.setdefault(f"{league}|{component}", []).append(
                (mean_age, n / DENOMINATOR, actual - mean, variance / n)
            )
    return out


def _strata(rows: list, index: int) -> list[list]:
    ordered = sorted(rows, key=lambda r: r[index])
    size = len(ordered) // STRATA
    if size == 0:
        return []
    return [
        ordered[k * size : (k + 1) * size if k < STRATA - 1 else len(ordered)]
        for k in range(STRATA)
    ]


def _summarise(group: list, alpha: float, tau2: float, by: str) -> dict[str, object]:
    base = [r[2] / (r[3] + tau2) ** 0.5 for r in group]
    cand = [r[2] / (r[3] + tau2 + alpha * r[0]) ** 0.5 for r in group]
    n = len(group)
    return {
        "n": n,
        "stratified_by": by,
        "mean_age_days": round(sum(r[0] for r in group) / n, 3),
        "mean_coverage": round(sum(r[1] for r in group) / n, 4),
        "baseline_var_z": round(sum(z * z for z in base) / n, 6),
        "candidate_var_z": round(sum(z * z for z in cand) / n, 6),
    }


def basis(pit: bool) -> dict[str, object]:
    cells: dict[str, object] = {}
    total_states = 0
    for component in ("attack", "defence"):
        produced = states(component, pit=pit)
        for cell, rows in sorted(produced.items()):
            total_states += len(rows)
            if len(rows) < MIN_STATES:
                cells[cell] = {"status": "INSUFFICIENT_STATES", "states": len(rows)}
                continue
            series = [
                sorted(s)
                for (lg, _t, _s), s in __import__("_load").load(component).items()
                if lg == cell.split("|")[0] and len(s) >= 3
            ]
            alpha, tau2, _ll = M.fit_full(series)
            age = [_summarise(g, alpha, tau2, "age") for g in _strata(rows, 0)]
            cov = [_summarise(g, alpha, tau2, "coverage") for g in _strata(rows, 1)]
            cells[cell] = {
                "status": "OK",
                "states": len(rows),
                "alpha_used": alpha,
                "tau2_used": tau2,
                "coverage_min": round(min(r[1] for r in rows), 4),
                "coverage_max": round(max(r[1] for r in rows), 4),
                "by_age": age,
                "by_coverage": cov,
                "baseline_var_z_oldest_minus_youngest": (
                    round(age[-1]["baseline_var_z"] - age[0]["baseline_var_z"], 6)
                    if len(age) == STRATA
                    else None
                ),
            }
    if total_states == 0:
        return {
            "status": "NOT_IDENTIFIABLE",
            "reason": (
                "no evaluation epoch carries three xG observations under this basis, "
                "so no calibration state can be formed"
            ),
        }
    return {"status": "COMPUTED", "total_states": total_states, "cells": cells}


def report() -> dict[str, object]:
    return {
        "window_semantics": (
            "latest 20 expected fixtures by kickoff across seasons, no season reset, "
            "matching team_xg_matches_for_teams(limit_per_team=20)"
        ),
        "coverage_definition": "|O| / |E| with E the expected window and O its xG-carrying subset",
        "baseline_is_coefficient_free": (
            "baseline z uses only SE0 and tau^2, so its trend across strata is a fact "
            "about prediction error rather than a property of any fitted model"
        ),
        "candidate_is_circular": "alpha comes from the same estimation period; in-sample only",
        "static_basis": basis(pit=False),
        "pit_basis": basis(pit=True),
    }


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, sort_keys=True))
