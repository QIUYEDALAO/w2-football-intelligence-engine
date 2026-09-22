#!/usr/bin/env python3
"""Offline, read-only Candidate A fit for total calibration.

This script consumes frozen CSV exports only.  It never opens a database or
provider connection.  The objective is the preregistered scoreline Poisson
NLL with hierarchical ridge shrinkage; production parameters are not touched.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(home_away: Path, team_xg: Path) -> list[dict[str, float | str]]:
    identities = {r["fixture_id"]: r for r in csv.DictReader(home_away.open(newline="", encoding="utf-8"))}
    by_fixture: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in csv.DictReader(team_xg.open(newline="", encoding="utf-8")):
        by_fixture[row["fixture_id"]][row["team_id"]] = row
    history: dict[str, list[dict[str, str]]] = defaultdict(list)
    out: list[dict[str, float | str]] = []
    ordered = sorted(by_fixture.items(), key=lambda item: (min(r["kickoff_at"] for r in item[1].values()), item[0]))
    for fixture_id, teams in ordered:
        identity = identities.get(fixture_id)
        if identity is None:
            continue
        home = teams.get(identity["home_id"])
        away = teams.get(identity["away_id"])
        if home is None or away is None:
            continue
        home_prior = history[identity["home_id"]]
        away_prior = history[identity["away_id"]]
        if len(home_prior) >= 5 and len(away_prior) >= 5:
            h = home_prior[-5:]
            a = away_prior[-5:]
            home_for = sum(float(r["xg_for"]) for r in h) / 5
            home_against = sum(float(r["xg_against"]) for r in h) / 5
            away_for = sum(float(r["xg_for"]) for r in a) / 5
            away_against = sum(float(r["xg_against"]) for r in a) / 5
            out.append({
                "fixture_id": fixture_id,
                "league_id": identity["league_id"],
                "kickoff_at": home["kickoff_at"],
                "base_home": (home_for + away_against) / 2,
                "base_away": (away_for + home_against) / 2,
                "goals_home": float(home["goals_for"]),
                "goals_away": float(home["goals_against"]),
            })
        home_prior.append(home)
        away_prior.append(away)
    return out


def clamp(x: float, lo: float, hi: float) -> float:
    return min(max(x, lo), hi)


HOME_ADVANTAGE_GOALS = 0.30
OOF_FOLDS = 4


def objective_and_gradient(rows, leagues, p, reg_total=5.0):
    total_scale = p[0]
    lt = {league: p[1 + i] for i, league in enumerate(leagues)}
    grad = [0.0] * len(p)
    hdiag = [1e-6] * len(p)
    value = 0.0
    for row in rows:
        league = row["league_id"]
        raw_total = clamp(float(row["base_home"]) + float(row["base_away"]), 1.35, 4.40)
        total = clamp(raw_total * total_scale * lt[league], 1.35, 4.40)
        delta = float(row["base_home"]) - float(row["base_away"]) + HOME_ADVANTAGE_GOALS
        home = clamp((total + delta) / 2, 0.15, 4.25)
        away = clamp((total - delta) / 2, 0.15, 4.25)
        gh, ga = float(row["goals_home"]), float(row["goals_away"])
        value += home - gh * math.log(home) + math.lgamma(gh + 1) + away - ga * math.log(away) + math.lgamma(ga + 1)
        dh = 0.0 if home in (0.15, 4.25) else 1.0 - gh / home
        da = 0.0 if away in (0.15, 4.25) else 1.0 - ga / away
        dtotal, ddelta = 0.5 * (dh + da), 0.5 * (dh - da)
        li = leagues.index(league)
        total_feature = dtotal * raw_total * lt[league] if 1.35 < raw_total * total_scale * lt[league] < 4.40 else 0.0
        league_total_feature = dtotal * raw_total * total_scale if total_feature else 0.0
        grad[0] += total_feature
        grad[1 + li] += league_total_feature
        curvature = max(1e-6, gh / (home * home) + ga / (away * away))
        hdiag[0] += curvature * (0.5 * raw_total * lt[league]) ** 2
        hdiag[1 + li] += curvature * (0.5 * raw_total * total_scale) ** 2
    for i, league in enumerate(leagues):
        grad[0] += 2 * reg_total * (total_scale - lt[league])
        grad[1 + i] += 2 * reg_total * (lt[league] - total_scale)
        hdiag[0] += 2 * reg_total
        hdiag[1 + i] += 2 * reg_total
        value += reg_total * (lt[league] - total_scale) ** 2
    return value, grad, hdiag


def fit(rows, leagues):
    p = [1.0] + [1.0] * len(leagues)
    bounds = [(0.8, 1.3)] + [(0.7, 1.4)] * len(leagues)
    history = []
    value, grad, hdiag = objective_and_gradient(rows, leagues, p)
    initial_value = value
    for iteration in range(1, 1001):
        norm = math.sqrt(sum(g * g for g in grad))
        if norm < 1e-5:
            return p, initial_value, history + [{"iteration": iteration, "objective": value, "gradient_norm": norm, "status": "CONVERGED_GRADIENT_TOL"}]
        step = 1.0
        accepted = False
        while step >= 1e-10:
            candidate = [clamp(x - step * g / max(h, 1e-6), lo, hi) for x, g, h, (lo, hi) in zip(p, grad, hdiag, bounds)]
            candidate_value, candidate_grad, candidate_hdiag = objective_and_gradient(rows, leagues, candidate)
            if candidate_value < value - 1e-8:
                p, value, grad, hdiag = candidate, candidate_value, candidate_grad, candidate_hdiag
                accepted = True
                break
            step *= 0.5
        history.append({"iteration": iteration, "objective": value, "gradient_norm": norm, "step": step, "accepted": accepted})
        if not accepted:
            recent = [r["objective"] for r in history[-3:]]
            status = "CONVERGED_OBJECTIVE_TOL" if recent and max(recent) - min(recent) < 1e-6 else "STALLED"
            return p, initial_value, history + [{"iteration": iteration, "objective": value, "gradient_norm": norm, "status": status}]
    return p, initial_value, history + [{"iteration": 1000, "objective": value, "gradient_norm": math.sqrt(sum(g * g for g in grad)), "status": "MAX_ITER"}]


def unpenalized_nll(rows, leagues, p):
    total_scale = p[0]
    lt = {league: p[1 + i] for i, league in enumerate(leagues)}
    value = 0.0
    for row in rows:
        league = row["league_id"]
        raw_total = clamp(float(row["base_home"]) + float(row["base_away"]), 1.35, 4.40)
        total = clamp(raw_total * total_scale * lt[league], 1.35, 4.40)
        delta = float(row["base_home"]) - float(row["base_away"]) + HOME_ADVANTAGE_GOALS
        home = clamp((total + delta) / 2, 0.15, 4.25)
        away = clamp((total - delta) / 2, 0.15, 4.25)
        gh, ga = float(row["goals_home"]), float(row["goals_away"])
        value += home - gh * math.log(home) + math.lgamma(gh + 1) + away - ga * math.log(away) + math.lgamma(ga + 1)
    return value


def lambdas(row, leagues, params):
    league = str(row["league_id"])
    raw_total = clamp(float(row["base_home"]) + float(row["base_away"]), 1.35, 4.40)
    league_scale = params[1 + leagues.index(league)] if league in leagues else 1.0
    total = clamp(raw_total * params[0] * league_scale, 1.35, 4.40)
    delta = float(row["base_home"]) - float(row["base_away"]) + HOME_ADVANTAGE_GOALS
    return clamp((total + delta) / 2, 0.15, 4.25), clamp((total - delta) / 2, 0.15, 4.25), total


def baseline_lambdas(row):
    raw_total = clamp(float(row["base_home"]) + float(row["base_away"]), 1.35, 4.40)
    delta = float(row["base_home"]) - float(row["base_away"]) + HOME_ADVANTAGE_GOALS
    return clamp((raw_total + delta) / 2, 0.15, 4.25), clamp((raw_total - delta) / 2, 0.15, 4.25), raw_total


def scoreline_nll(row, values):
    home, away, _ = values
    gh, ga = int(float(row["goals_home"])), int(float(row["goals_away"]))
    return home - gh * math.log(home) + math.lgamma(gh + 1) + away - ga * math.log(away) + math.lgamma(ga + 1)


def one_x_two_brier(row, values):
    home, away, _ = values
    gh, ga = int(float(row["goals_home"])), int(float(row["goals_away"]))
    probs = [0.0, 0.0, 0.0]
    for h in range(11):
        for a in range(11):
            p = math.exp(-home + h * math.log(home) - math.lgamma(h + 1)) * math.exp(-away + a * math.log(away) - math.lgamma(a + 1))
            probs[0 if h > a else 1 if h == a else 2] += p
    actual = [1.0 if gh > ga else 0.0, 1.0 if gh == ga else 0.0, 1.0 if gh < ga else 0.0]
    return sum((p - y) ** 2 for p, y in zip(probs, actual)) / 3.0


def oof_metrics(rows, leagues, params, baseline=True):
    if not rows:
        return {"n": 0, "mean_nll": None, "total_abs_gap": None, "league_n_ge_20_abs_gap_median": None, "brier_1x2": None}
    nll = []
    brier = []
    totals = []
    leagues_totals = defaultdict(list)
    for row in rows:
        values = baseline_lambdas(row) if baseline else lambdas(row, leagues, params)
        nll.append(scoreline_nll(row, values))
        brier.append(one_x_two_brier(row, values))
        actual = float(row["goals_home"]) + float(row["goals_away"])
        totals.append(values[2] - actual)
        leagues_totals[str(row["league_id"])].append(values[2] - actual)
    eligible = [abs(sum(v) / len(v)) for v in leagues_totals.values() if len(v) >= 20]
    eligible.sort()
    median = None if not eligible else eligible[(len(eligible) - 1) // 2] if len(eligible) % 2 else (eligible[len(eligible)//2 - 1] + eligible[len(eligible)//2]) / 2
    return {"n": len(rows), "mean_nll": round(sum(nll) / len(nll), 12), "total_abs_gap": round(abs(sum(totals) / len(totals)), 12), "league_n_ge_20_abs_gap_median": round(median, 12) if median is not None else None, "brier_1x2": round(sum(brier) / len(brier), 12)}


def rolling_origin_oof(rows, leagues):
    rows = sorted(rows, key=lambda r: (str(r["kickoff_at"]), str(r["fixture_id"])))
    boundaries = [round(len(rows) * i / OOF_FOLDS) for i in range(OOF_FOLDS + 1)]
    folds = []
    raw_records, candidate_records = [], []
    for fold in range(1, OOF_FOLDS):
        train, valid = rows[:boundaries[fold]], rows[boundaries[fold]:boundaries[fold + 1]]
        params, _, _ = fit(train, sorted({str(r["league_id"]) for r in train}))
        fold_leagues = sorted({str(r["league_id"]) for r in train})
        raw_records.extend((r, baseline_lambdas(r)) for r in valid)
        candidate_records.extend((r, lambdas(r, fold_leagues, params)) for r in valid)
        folds.append({"fold": fold, "train_n": len(train), "valid_n": len(valid), "candidate_scored_n": len(valid), "raw": oof_metrics(valid, fold_leagues, params, True), "candidate": oof_metrics(valid, fold_leagues, params, False)})
    def records_metrics(records):
        if not records:
            return {"n": 0, "mean_nll": None, "total_abs_gap": None, "league_n_ge_20_abs_gap_median": None, "brier_1x2": None}
        values = []
        for row, params_values in records:
            values.append((row, params_values, scoreline_nll(row, params_values), one_x_two_brier(row, params_values), params_values[2] - float(row["goals_home"]) - float(row["goals_away"])))
        by_league = defaultdict(list)
        for row, _, _, _, diff in values:
            by_league[str(row["league_id"])].append(diff)
        medians = sorted(abs(sum(v) / len(v)) for v in by_league.values() if len(v) >= 20)
        median = None if not medians else medians[(len(medians)-1)//2] if len(medians) % 2 else (medians[len(medians)//2-1] + medians[len(medians)//2]) / 2
        return {"n": len(values), "mean_nll": round(sum(v[2] for v in values) / len(values), 12), "total_abs_gap": round(abs(sum(v[4] for v in values) / len(values)), 12), "league_n_ge_20_abs_gap_median": round(median, 12) if median is not None else None, "brier_1x2": round(sum(v[3] for v in values) / len(values), 12)}
    return {"folds": folds, "fold_count": OOF_FOLDS, "raw": records_metrics(raw_records), "candidate": records_metrics(candidate_records)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--home-away", type=Path, required=True)
    ap.add_argument("--team-xg", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    rows = load(args.home_away, args.team_xg)
    leagues = sorted({str(r["league_id"]) for r in rows})
    params, initial_objective, convergence = fit(rows, leagues)
    baseline_params = [1.0] + [1.0] * len(leagues)
    baseline_nll = unpenalized_nll(rows, leagues, baseline_params)
    candidate_nll = unpenalized_nll(rows, leagues, params)
    oof = rolling_origin_oof(rows, leagues)
    payload = {
        "schema": "w2.candidate_a.offline_fit.v2",
        "status": "FITTED_CALIBRATED",
        "data_role": "TRAIN_ONLY_OFFLINE",
        "fit_method": {"objective": "Poisson scoreline NLL + hierarchical ridge", "optimizer": "projected normalized-gradient with backtracking", "lambda_reg_total": 5.0, "home_advantage_goals": {"fixed": HOME_ADVANTAGE_GOALS, "source": "V1-HOME-ADVANTAGE-RECALIBRATION-01 APPROVED_VALIDATED"}, "bounds": {"total_scale": [0.8, 1.3], "league_total_scale": [0.7, 1.4]}, "oof_folds": OOF_FOLDS, "oof_split": "ascending TRAIN divided into four contiguous blocks; each fold trains on all earlier blocks and scores the next block"},
        "manifest": {"fixture_count": len(rows), "league_count": len(leagues), "fixture_ids_sha256": hashlib.sha256("\n".join(sorted(str(r["fixture_id"]) for r in rows)).encode()).hexdigest(), "home_away_sha256": sha256(args.home_away), "team_xg_sha256": sha256(args.team_xg)},
        "parameters": {"total_scale": round(params[0], 6), "home_advantage_goals": HOME_ADVANTAGE_GOALS, "league_total_scale": {l: round(params[1+i], 6) for i, l in enumerate(leagues)}},
        "nll_convergence": {"iterations": len(convergence), "initial_penalized_objective": initial_objective, "final": convergence[-1], "trace_tail": convergence[-10:], "baseline_unpenalized_nll": baseline_nll, "candidate_unpenalized_nll": candidate_nll, "baseline_mean_nll": baseline_nll / len(rows), "candidate_mean_nll": candidate_nll / len(rows)},
        "oof": oof,
        "safety": {"provider_calls": 0, "production_writes": 0, "deployments": 0, "calibration_ledger_writes": 0, "production_status": "BASELINE_PRIOR"},
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "fixture_count": len(rows), "iterations": len(convergence), "parameters": payload["parameters"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
