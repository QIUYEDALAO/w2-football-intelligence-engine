#!/usr/bin/env python3
"""The authoritative production evaluation-epoch population, with three guards.

Protocol v6 sections 3 and 4 (commit b74766f9).

An epoch is a `(team, fixture)` pair at that fixture's kickoff, drawn from every
finished fixture in the corpus. Admission depends only on what is knowable then:
the latest 20 xG rows before the kickoff, across seasons, at least three of them,
positive sample variance -- which is where `_xg_standard_error` fails closed.

v5 walked the xG-carrying series instead and made each of *those* kickoffs an
epoch, so an epoch existed only where the target fixture happened to produce xG
afterwards. That is a condition nobody has at decision time, and it dropped 40% of
the population. Whether the target produced xG is needed only to score a residual,
so calibration may restrict to those epochs and must say so; nothing else may.

    python3 scripts/ev_se_v6_epochs.py                 # self-check
    python3 scripts/ev_se_v6_epochs.py --prove-it-fails # negative controls
"""
from __future__ import annotations

import bisect
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))
import ev_se_v5_window as W
from _load import CORPUS

DENOMINATOR = W.DENOMINATOR
MIN_OBSERVED = W.MIN_OBSERVED


def analysis_epochs(
    component: str,
    *,
    pit: bool = False,
    season_reset: bool = False,
    require_target_xg: bool = False,
    ignore_capture: bool = False,
) -> dict[str, Any]:
    """Epochs plus the admission ledger.

    The three keyword flags exist only so `self_check` can build each known
    regression deliberately and confirm the guard notices. Production code passes
    none of them.
    """
    observed = W.observed_timelines(component)
    expected = W.expected_timelines()
    seasons: dict[tuple[str, str], str] = {}
    if season_reset:
        for row in json.load(open(CORPUS))["history_rows"]:
            seasons[(row["provider_fixture_id"], row["team_id"])] = row["season"]

    cells: dict[str, list[dict[str, Any]]] = {}
    ledger = {
        "candidate_team_fixture_pairs": 0,
        "excluded_no_xg_history_for_team": 0,
        "excluded_window_below_three": 0,
        "excluded_zero_variance": 0,
        "excluded_target_without_xg": 0,
        "admitted": 0,
    }
    for (league, team), fixtures in expected.items():
        history = observed.get((league, team), [])
        times = [row[0] for row in history]
        by_fixture = {row[2]: row for row in history}
        for as_of, fixture in fixtures:
            ledger["candidate_team_fixture_pairs"] += 1
            if not history:
                ledger["excluded_no_xg_history_for_team"] += 1
                continue
            target = by_fixture.get(fixture)
            if require_target_xg and target is None:
                ledger["excluded_target_without_xg"] += 1
                continue
            cut = bisect.bisect_left(times, as_of)
            window = history[max(0, cut - DENOMINATOR) : cut]
            if season_reset:
                current = seasons.get((fixture, team))
                window = [
                    row for row in window if seasons.get((row[2], team)) == current
                ]
            if pit and not ignore_capture:
                window = [row for row in window if row[3] <= as_of]
            if len(window) < MIN_OBSERVED:
                ledger["excluded_window_below_three"] += 1
                continue
            values = [row[1] for row in window]
            n = len(values)
            mean = sum(values) / n
            variance = sum((v - mean) ** 2 for v in values) / (n - 1)
            if variance <= 0:
                ledger["excluded_zero_variance"] += 1
                continue
            ledger["admitted"] += 1
            cells.setdefault(f"{league}|{component}", []).append(
                {
                    "mean_age_days": sum(as_of - row[0] for row in window) / n,
                    "se0_squared": variance / n,
                    "observed": n,
                    "target_has_xg": target is not None,
                    "residual": (target[1] - mean) if target is not None else None,
                }
            )
    return {"cells": cells, "ledger": ledger}


def _shape(result: dict[str, Any]) -> tuple[int, float]:
    ages = sorted(
        s["mean_age_days"] for v in result["cells"].values() for s in v
    )
    if not ages:
        return 0, 0.0
    spread = ages[int(0.9 * len(ages))] - ages[int(0.1 * len(ages))]
    return result["ledger"]["admitted"], float(spread)


def self_check() -> dict[str, Any]:
    """The production population must differ from all three regressions."""
    base = analysis_epochs("attack")
    base_n, base_spread = _shape(base)
    findings: list[str] = []

    reset_n, reset_spread = _shape(analysis_epochs("attack", season_reset=True))
    if base_n <= reset_n or base_spread <= reset_spread * 1.5:
        findings.append("season_reset_indistinguishable_from_production_population")

    target_n, _ = _shape(analysis_epochs("attack", require_target_xg=True))
    if base_n <= target_n:
        findings.append("target_xg_conditioning_indistinguishable_from_production")

    pit_n, _ = _shape(analysis_epochs("attack", pit=True))
    leak_n, _ = _shape(analysis_epochs("attack", pit=True, ignore_capture=True))
    if pit_n >= leak_n:
        findings.append("pit_basis_admits_as_many_epochs_as_one_ignoring_captured_at")

    return {
        "production_epochs": base_n,
        "production_age_spread_p10_p90_days": round(base_spread, 3),
        "season_reset_epochs": reset_n,
        "season_reset_age_spread_p10_p90_days": round(reset_spread, 3),
        "target_xg_conditioned_epochs": target_n,
        "epochs_lost_to_target_conditioning": base_n - target_n,
        "pit_epochs": pit_n,
        "capture_ignoring_epochs": leak_n,
        "ledger": base["ledger"],
        "findings": findings,
        "result": "PASS" if not findings else "FAIL",
    }


def prove_check_bites() -> dict[str, Any]:
    """Inject each regression into the production constructor and confirm a failure."""
    scope = globals()
    original = scope["analysis_epochs"]
    outcomes: dict[str, Any] = {}
    injections = {
        "season_reset": {"season_reset": True},
        "target_xg_conditioning": {"require_target_xg": True},
        "future_capture_leak": {"ignore_capture": True},
    }
    for name, override in injections.items():
        def injected(
            component: str, _override: dict[str, Any] = override, **kwargs: Any
        ) -> dict[str, Any]:
            result: dict[str, Any] = original(component, **{**kwargs, **_override})
            return result

        scope["analysis_epochs"] = injected
        try:
            broken = self_check()
        finally:
            scope["analysis_epochs"] = original
        outcomes[name] = {
            "result": broken["result"], "findings": broken["findings"],
            "guard_bites": broken["result"] == "FAIL",
        }
    return {
        "injections": outcomes,
        "all_guards_bite": all(v["guard_bites"] for v in outcomes.values()),
    }


if __name__ == "__main__":
    if "--prove-it-fails" in sys.argv:
        proof = prove_check_bites()
        print(json.dumps(proof, indent=2, sort_keys=True))
        raise SystemExit(0 if proof["all_guards_bite"] else 1)
    report = self_check()
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["result"] == "PASS" else 1)
