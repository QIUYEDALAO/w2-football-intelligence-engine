#!/usr/bin/env python3
"""Supplementary diagnostic: is the detected drift really drift?

DISCLOSURE: this check was added after the primary v3 estimates were read. It does
not replace them and it changes no frozen number. It exists because the local level
model attributes every slow-moving component of a team's xG series to latent
strength, and two fixture-level covariates it does not carry can imitate that:

  * home advantage -- xG_for is systematically higher at home, so any run of home
    or away fixtures shifts the series without the team changing;
  * opponent quality -- facing weak opponents raises xG_for, and schedules are not
    randomly ordered.

If a cell's drift survives removing both, the drift is about the team. If it
collapses, the model was reading the calendar.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import ev_se_mle as M
from _load import CORPUS, CSV, LEAGUE
from ev_se_drift_alpha import HOLDOUT_CUTOFF, parse_ts


def sides_and_opponents() -> dict[tuple[str, str], tuple[str, str]]:
    out: dict[tuple[str, str], tuple[str, str]] = {}
    for row in json.load(open(CORPUS))["history_rows"]:
        out[(row["provider_fixture_id"], row["team_id"])] = (
            row["team_side"],
            row["opponent_team_id"],
        )
    return out


def load_rich(component: str) -> dict[str, list[tuple[str, str, float, float, str, str]]]:
    """cell -> [(team, season, t, y, side, opponent), ...] over the estimation period."""
    meta = sides_and_opponents()
    key: dict[tuple[str, str], tuple[str, str]] = {}
    for row in json.load(open(CORPUS))["history_rows"]:
        key[(row["provider_fixture_id"], row["team_id"])] = (
            row["provider_league_id"],
            row["season"],
        )
    col = 4 if component == "attack" else 5
    out: dict[str, list] = {}
    for line in open(CSV):
        p = line.rstrip("\n").split(",")
        if len(p) != 7 or p[0] in ("BEGIN", "ROLLBACK"):
            continue
        if p[2] >= HOLDOUT_CUTOFF:
            continue
        info = key.get((p[0], p[1]))
        side = meta.get((p[0], p[1]))
        if info is None or side is None:
            continue
        league = LEAGUE.get(info[0])
        if league is None:
            continue
        out.setdefault(f"{league}|{component}", []).append(
            (p[1], info[1], parse_ts(p[2]), float(p[col]), side[0], side[1])
        )
    return out


def _centre(rows: list, index: int, values: list[float]) -> list[float]:
    """Remove a categorical fixed effect by centring within its level."""
    groups: dict[str, list[float]] = {}
    for row, value in zip(rows, values, strict=True):
        groups.setdefault(row[index], []).append(value)
    means = {k: sum(v) / len(v) for k, v in groups.items()}
    overall = sum(values) / len(values)
    return [
        value - means[row[index]] + overall
        for row, value in zip(rows, values, strict=True)
    ]


def series_from(rows: list, values: list[float]) -> list[list[tuple[float, float]]]:
    grouped: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for row, value in zip(rows, values, strict=True):
        grouped.setdefault((row[0], row[1]), []).append((row[2], value))
    return [sorted(s) for s in grouped.values() if len(s) >= 3]


def fit(series: list[list[tuple[float, float]]]) -> tuple[float, float]:
    sigma2, _tau2, ll_full = M.fit_full(series)
    _t, ll_null = M.fit_restricted(series)
    return sigma2, M.lrt_pvalue(ll_full, ll_null)


def report() -> dict[str, object]:
    out: dict[str, object] = {}
    for component in ("attack", "defence"):
        for cell, rows in sorted(load_rich(component).items()):
            raw = [r[3] for r in rows]
            s_raw, p_raw = fit(series_from(rows, raw))
            side_adj = _centre(rows, 4, raw)                 # index 4 = HOME/AWAY
            s_side, p_side = fit(series_from(rows, side_adj))
            both_adj = _centre(rows, 5, side_adj)            # index 5 = opponent
            s_both, p_both = fit(series_from(rows, both_adj))
            out[cell] = {
                "observations": len(rows),
                "raw": {"sigma2": s_raw, "p": p_raw},
                "home_away_adjusted": {"sigma2": s_side, "p": p_side},
                "home_away_and_opponent_adjusted": {"sigma2": s_both, "p": p_both},
                "survives_adjustment": bool(p_both < 0.05),
                "sigma2_retained_fraction": (s_both / s_raw) if s_raw > 0 else None,
            }
    return {
        "disclosure": (
            "added after the primary v3 estimates were read; supplementary only, "
            "and it changes no frozen number"
        ),
        "adjustments": ["home/away fixed effect", "opponent fixed effect"],
        "cells": out,
    }


def main() -> int:
    print(json.dumps(report(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
