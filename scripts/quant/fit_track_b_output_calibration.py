#!/usr/bin/env python3
"""Read-only Track B output calibration on a frozen TRAIN CSV export.

This script deliberately has no database, provider, ledger, or production-module
imports.  It fits two preregistered output calibrators on TRAIN only:

* hierarchical isotonic: competition x market x selection cells shrink smoothly
  toward an independent market x selection global curve; and
* a selection-aware Platt baseline.

The model family is selected per market x selection by deterministic expanding-time
OOF Brier score (NLL breaks ties).  Holdout/test files are not accepted by the
interface and are never read or scored here.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pava(xs: list[float], ys: list[float]) -> list[tuple[float, float]]:
    """Return ``(right_edge_x, fitted_y)`` blocks for non-decreasing PAVA.

    The right edge, not the block mean, is the threshold used by ``predict``.
    Equal-x observations are aggregated first so serialized edges are strictly
    increasing and the prediction contract is deterministic.
    """
    if len(xs) != len(ys):
        raise ValueError("PAVA inputs must have equal length")
    grouped: dict[float, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for x, y in zip(xs, ys):
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError("PAVA inputs must be finite")
        grouped[float(x)][0] += float(y)
        grouped[float(x)][1] += 1.0
    blocks: list[list[float]] = []  # left_edge, right_edge, y_sum, n
    for x in sorted(grouped):
        y_sum, n = grouped[x]
        blocks.append([x, x, y_sum, n])
        while len(blocks) >= 2:
            a, b = blocks[-2], blocks[-1]
            if a[2] / a[3] <= b[2] / b[3]:
                break
            blocks[-2] = [a[0], b[1], a[2] + b[2], a[3] + b[3]]
            blocks.pop()
    return [(b[1], b[2] / b[3]) for b in blocks]


def predict(curve: list[tuple[float, float]], x: float) -> float:
    if not curve:
        return 0.5
    # A block owns x values up to and including its right edge.  The first edge
    # at or above the input therefore selects the fitted block; this preserves
    # every observed x in its PAVA block and makes max(x) operational.
    knots = [knot for knot, _ in curve]
    index = bisect.bisect_left(knots, x)
    return curve[min(index, len(curve) - 1)][1]


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-min(value, 700.0))
        return 1.0 / (1.0 + z)
    z = math.exp(max(value, -700.0))
    return z / (1.0 + z)


def _logit(value: float) -> float:
    p = min(max(float(value), 1e-6), 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


def fit_platt(rows: list[dict]) -> dict[str, float]:
    """Fit monotone logistic calibration ``sigmoid(intercept + slope*logit(p))``."""
    if not rows:
        return {"intercept": 0.0, "slope": 1.0, "n": 0}
    xs = [_logit(float(row["model_probability"])) for row in rows]
    ys = [float(row["y"]) for row in rows]
    intercept, slope = 0.0, 1.0
    ridge = 1e-8
    for _ in range(100):
        grad_a = grad_b = h_aa = h_ab = h_bb = 0.0
        for x, y in zip(xs, ys):
            p = _sigmoid(intercept + slope * x)
            weight = p * (1.0 - p)
            error = p - y
            grad_a += error
            grad_b += error * x
            h_aa += weight
            h_ab += weight * x
            h_bb += weight * x * x
        h_aa += ridge
        h_bb += ridge
        determinant = h_aa * h_bb - h_ab * h_ab
        if determinant <= 1e-14:
            break
        step_a = (h_bb * grad_a - h_ab * grad_b) / determinant
        step_b = (-h_ab * grad_a + h_aa * grad_b) / determinant
        new_intercept = min(20.0, max(-20.0, intercept - step_a))
        new_slope = min(20.0, max(0.0, slope - step_b))
        if abs(new_intercept - intercept) + abs(new_slope - slope) < 1e-10:
            intercept, slope = new_intercept, new_slope
            break
        intercept, slope = new_intercept, new_slope
    return {"intercept": round(intercept, 12), "slope": round(slope, 12), "n": len(rows)}


def predict_platt(params: dict[str, float], probability: float) -> float:
    return _sigmoid(float(params["intercept"]) + float(params["slope"]) * _logit(probability))


def _curve_json(curve: list[tuple[float, float]]) -> list[dict[str, float]]:
    return [{"right_edge": round(x, 12), "y": round(y, 12)} for x, y in curve]


def _curve_is_valid(curve: list[tuple[float, float]]) -> bool:
    return all(
        left < right and 0.0 <= left_y <= right_y <= 1.0
        for (left, left_y), (right, right_y) in zip(curve, curve[1:])
    ) and all(0.0 <= y <= 1.0 for _, y in curve)


def _fit_hierarchical_maps(rows: list[dict], k: float) -> tuple[dict[tuple[str, str], list[tuple[float, float]]], dict[tuple[str, str, str], list[tuple[float, float]]]]:
    global_curves: dict[tuple[str, str], list[tuple[float, float]]] = {}
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["market"], row["selection"], row["competition_id"])].append(row)
    for key in sorted({(r["market"], r["selection"]) for r in rows}):
        subset = [r for r in rows if (r["market"], r["selection"]) == key]
        global_curves[key] = fit_curve(subset)
    cell_curves = {key: fit_curve(cell) for key, cell in groups.items()}
    return global_curves, cell_curves


def _predict_hierarchical(row: dict, global_curves: dict, cell_curves: dict, k: float, cell_n: int) -> float:
    pair = (row["market"], row["selection"])
    cell_key = (row["market"], row["selection"], row["competition_id"])
    global_curve = global_curves.get(pair, [])
    cell_curve = cell_curves.get(cell_key, [])
    p_global = predict(global_curve, float(row["model_probability"]))
    p_cell = predict(cell_curve, float(row["model_probability"])) if cell_curve else p_global
    weight = cell_n / (cell_n + k) if cell_n else 0.0
    return weight * p_cell + (1.0 - weight) * p_global


def _metrics(rows: list[dict], predictions: list[float]) -> dict[str, float]:
    if not rows:
        return {"n": 0, "cal_gap": None, "brier": None, "nll": None}
    gap = sum(p - float(row["y"]) for row, p in zip(rows, predictions)) / len(rows)
    brier = sum((p - float(row["y"])) ** 2 for row, p in zip(rows, predictions)) / len(rows)
    nll = -sum(
        float(row["y"]) * math.log(min(max(p, 1e-9), 1.0 - 1e-9))
        + (1.0 - float(row["y"])) * math.log(min(max(1.0 - p, 1e-9), 1.0 - 1e-9))
        for row, p in zip(rows, predictions)
    ) / len(rows)
    return {"n": len(rows), "cal_gap": round(gap, 12), "brier": round(brier, 12), "nll": round(nll, 12)}


def _temporal_oof(rows: list[dict], k: float, folds: int = 5) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], dict]]:
    """Expanding-time OOF model selection, with no future row in a fit."""
    by_pair: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        by_pair[(row["market"], row["selection"])].append(row)
    selected: dict[tuple[str, str], str] = {}
    diagnostics: dict[tuple[str, str], dict] = {}
    for pair, pair_rows in sorted(by_pair.items()):
        pair_rows = sorted(pair_rows, key=lambda r: (r["evaluated_at"], r["fixture_id"], r["competition_id"]))
        predictions = {"hierarchical_isotonic": [], "platt": [], "raw": []}
        observed: list[dict] = []
        n = len(pair_rows)
        if n >= folds * 2:
            boundaries = [round(n * i / folds) for i in range(folds + 1)]
            for fold in range(1, folds):
                train_end, valid_end = boundaries[fold], boundaries[fold + 1]
                train = pair_rows[:train_end]
                valid = pair_rows[train_end:valid_end]
                if not train or not valid:
                    continue
                global_curves, cell_curves = _fit_hierarchical_maps(train, k)
                cell_sizes = defaultdict(int)
                for train_row in train:
                    cell_sizes[(train_row["market"], train_row["selection"], train_row["competition_id"])] += 1
                for row in valid:
                    cell_n = cell_sizes[(row["market"], row["selection"], row["competition_id"])]
                    predictions["hierarchical_isotonic"].append(_predict_hierarchical(row, global_curves, cell_curves, k, cell_n))
                platt = fit_platt(train)
                predictions["platt"].extend(predict_platt(platt, float(row["model_probability"])) for row in valid)
                predictions["raw"].extend(float(row["model_probability"]) for row in valid)
                observed.extend(valid)
        candidate_metrics = {name: _metrics(observed, values) for name, values in predictions.items()}
        if not observed:
            selected[pair] = "hierarchical_isotonic"
        else:
            selection_metrics = {
                name: candidate_metrics[name]
                for name in ("hierarchical_isotonic", "platt")
            }
            selected[pair] = min(
                selection_metrics,
                key=lambda name: (selection_metrics[name]["brier"], selection_metrics[name]["nll"], name),
            )
        diagnostics[pair] = {
            "oof_rows": len(observed),
            "folds": folds - 1,
            "candidates": {
                name: candidate_metrics[name]
                for name in ("hierarchical_isotonic", "platt")
            },
            "raw": candidate_metrics["raw"],
            "selected": selected[pair],
        }
    return selected, diagnostics


def atomic(line: float) -> list[float]:
    q = round(line * 4) / 4
    frac = round(q - int(q), 2)
    if frac in (0.25, 0.75):
        lo = round(q - 0.25, 2) if frac == 0.25 else round(q - 0.25, 2)
        hi = round(q + 0.25, 2)
        return [lo, hi]
    return [q]


def one_settlement(value: float) -> float:
    if value > 0:
        return 1.0
    if value == 0:
        return 0.0
    if value == -0.5:
        return -0.5
    return -1.0


def outcome(market: str, selection: str, line: float, home_goals: int, away_goals: int) -> float:
    values: list[float] = []
    if market == "TOTALS":
        total = home_goals + away_goals
        for component in atomic(line):
            signed = total - component
            values.append(one_settlement(signed if selection == "OVER" else -signed))
    elif market == "ASIAN_HANDICAP":
        margin = home_goals - away_goals if selection == "HOME" else away_goals - home_goals
        for component in atomic(line):
            values.append(one_settlement(margin + component))
    else:
        raise ValueError(f"unsupported market: {market}")
    return sum(values) / len(values)


def load_scores(home_away: Path, team_xg: Path) -> dict[str, tuple[int, int]]:
    identities = {r["fixture_id"]: r for r in csv.DictReader(home_away.open(newline="", encoding="utf-8"))}
    teams: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in csv.DictReader(team_xg.open(newline="", encoding="utf-8")):
        teams[row["fixture_id"]][row["team_id"]] = row
    result: dict[str, tuple[int, int]] = {}
    for fid, identity in identities.items():
        h = teams.get(fid, {}).get(identity["home_id"])
        a = teams.get(fid, {}).get(identity["away_id"])
        if h and a:
            result[fid] = (int(float(h["goals_for"])), int(float(a["goals_for"])))
    return result


def load_rows(evaluations: Path, scores: dict[str, tuple[int, int]]) -> tuple[list[dict], dict]:
    latest: dict[tuple[str, str], dict] = {}
    excluded_fixture_ids: set[str] = set()
    exclusion_reasons: dict[str, int] = defaultdict(int)
    excluded_rows = 0
    with evaluations.open(newline="", encoding="utf-8") as fh:
        first = fh.readline()
        fh.seek(0)
        admission_format = first.startswith("extract_at,") or first.startswith("evaluation_id,")
        iterator = csv.DictReader(fh) if admission_format else csv.reader(fh)
        for fields in iterator:
            if admission_format:
                p = fields
                try:
                    payload = json.loads(p.get("evaluation_payload") or p.get("payload") or "")
                except (json.JSONDecodeError, KeyError):
                    continue
                fid = str(p.get("fixture_id", payload.get("fixture_id", "")))
                if p.get("home_goals") not in (None, "") and p.get("away_goals") not in (None, ""):
                    scores[fid] = (int(float(p["home_goals"])), int(float(p["away_goals"])))
                stamp = (str(p.get("evaluated_at", "")), str(p.get("evaluation_id", "")))
            else:
                if len(fields) < 3:
                    continue
                payload = None
                for candidate in reversed(fields[2:]):
                    try:
                        parsed = json.loads(candidate)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(parsed, dict):
                        payload = parsed
                        break
                if payload is None:
                    continue
                fid = str(payload.get("fixture_id", fields[1]))
                stamp = (str(payload.get("evaluated_at", fields[0])), str(payload.get("evaluation_id", fields[0])))
            key = (fid, str(payload.get("market", fields.get("market", "") if admission_format else "")))
            if not key[1] or key[0] not in scores:
                continue
            if not payload.get("model_settlement_distribution"):
                excluded_rows += 1
                excluded_fixture_ids.add(key[0])
                exclusion_reasons["no_model_settlement_distribution"] += 1
                continue
            if payload.get("exact_line") is None or payload.get("selection") is None:
                continue
            current = latest.get(key)
            if current is None or stamp > current["_stamp"]:
                latest[key] = {"payload": payload, "_stamp": stamp}
    rows: list[dict] = []
    for item in latest.values():
        p = item["payload"]
        fid = str(p["fixture_id"])
        hg, ag = scores[fid]
        dist = p["model_settlement_distribution"]
        model_p = float(dist.get("WIN", 0.0)) + float(dist.get("HALF_WIN", 0.0))
        settlement = outcome(str(p["market"]), str(p["selection"]), float(p["exact_line"]), hg, ag)
        rows.append({
            "fixture_id": fid,
            "competition_id": str(p.get("competition_id") or "UNKNOWN"),
            "market": str(p["market"]),
            "selection": str(p["selection"]),
            "model_probability": model_p,
            "settlement": settlement,
            "y": 1.0 if settlement > 0 else 0.0,
            "evaluated_at": str(p.get("evaluated_at", "")),
        })
    return sorted(rows, key=lambda r: (r["evaluated_at"], r["fixture_id"], r["market"])), {
        "excluded_rows": excluded_rows,
        "excluded_fixtures": len(excluded_fixture_ids),
        "exclusion_reasons": dict(sorted(exclusion_reasons.items())),
        "excluded_fixture_ids": sorted(excluded_fixture_ids),
    }


def fit_curve(rows: list[dict]) -> list[tuple[float, float]]:
    return pava([r["model_probability"] for r in rows], [r["y"] for r in rows])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evaluations", type=Path, required=True)
    ap.add_argument("--home-away", type=Path, required=True)
    ap.add_argument("--team-xg", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    scores = load_scores(args.home_away, args.team_xg)
    rows, exclusions = load_rows(args.evaluations, scores)
    if not rows:
        raise SystemExit("no complete evaluation rows")
    k = 20.0
    global_curves, cell_curves = _fit_hierarchical_maps(rows, k)
    selected_models, oof = _temporal_oof(rows, k)
    pair_rows = {
        pair: [row for row in rows if (row["market"], row["selection"]) == pair]
        for pair in global_curves
    }
    platt_models = {pair: fit_platt(subset) for pair, subset in pair_rows.items()}
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["competition_id"], row["market"], row["selection"])].append(row)
    cells = []
    calibrated_rows = []
    for key, cell in sorted(groups.items()):
        market, selection = key[1], key[2]
        n = len(cell)
        w = n / (n + k)
        cell_key = (market, selection, key[0])
        cell_curve = cell_curves[cell_key]
        pair_curve = global_curves[(market, selection)]
        model = selected_models[(market, selection)]
        cell_calibrated = []
        for row in cell:
            if model == "platt":
                # final Platt baseline is fit on all TRAIN rows of this pair
                calibrated = predict_platt(platt_models[(market, selection)], float(row["model_probability"]))
            else:
                calibrated = _predict_hierarchical(row, global_curves, cell_curves, k, n)
            calibrated_rows.append((row, calibrated))
            cell_calibrated.append((row, calibrated))
        raw_gap = sum(r["model_probability"] - r["y"] for r in cell) / n
        cal_gap = sum(c - r["y"] for r, c in cell_calibrated) / n
        cells.append({
            "competition_id": key[0], "market": market, "selection": selection,
            "n": n, "weight": round(w, 12), "continuous_shrinkage": True,
            "raw_cal_gap": round(raw_gap, 12), "calibrated_cal_gap": round(cal_gap, 12),
            "raw_abs_cal_gap": round(abs(raw_gap), 12), "calibrated_abs_cal_gap": round(abs(cal_gap), 12),
            "curve": _curve_json(cell_curve),
            "global_curve": _curve_json(pair_curve),
            "selected_model": model,
        })
    raw_gap = sum(r["model_probability"] - r["y"] for r in rows) / len(rows)
    cal_gap = sum(c - r["y"] for r, c in calibrated_rows) / len(rows)
    payload = {
        "schema": "w2.track_b.output_calibration.offline_fit.v2",
        "status": "FITTED_CALIBRATED",
        "data_role": "TRAIN_ONLY_OFFLINE",
        "fit_method": {
            "model": "hierarchical PAVA isotonic + selection-aware Platt baseline",
            "stratification": ["competition_id", "market", "selection"],
            "global_prior": "market x selection",
            "pava_threshold": "right_edge=max(x) per fitted block",
            "min_cell_n": None,
            "shrinkage": "p_cal = n/(n+k)*p_cell + k/(n+k)*p_market_selection_global",
            "k": 20,
            "continuous_weight": "n/(n+k), all n",
            "selection_rule": "expanding-time OOF; Brier then NLL then model name",
            "oof_folds": 4,
        },
        "manifest": {"evaluation_sha256": sha256(args.evaluations), "home_away_sha256": sha256(args.home_away), "team_xg_sha256": sha256(args.team_xg), "independent_rows": len(rows), "fixtures": len({r["fixture_id"] for r in rows}), "cells": len(cells), **exclusions},
        "global_curves": {f"{market}|{selection}": _curve_json(curve) for (market, selection), curve in global_curves.items()},
        "platt_models": {f"{market}|{selection}": params for (market, selection), params in platt_models.items()},
        "selected_models": {f"{market}|{selection}": model for (market, selection), model in selected_models.items()},
        "oof_selection": {f"{market}|{selection}": details for (market, selection), details in oof.items()},
        "training_metrics": {"raw_cal_gap": round(raw_gap, 12), "calibrated_cal_gap": round(cal_gap, 12), "raw_abs_cal_gap": round(abs(raw_gap), 12), "calibrated_abs_cal_gap": round(abs(cal_gap), 12), "cells_abs_gap_improved": sum(c["calibrated_abs_cal_gap"] < c["raw_abs_cal_gap"] for c in cells), "cells_abs_gap_not_improved": sum(c["calibrated_abs_cal_gap"] >= c["raw_abs_cal_gap"] for c in cells)},
        "cells": cells,
        "safety": {"provider_calls": 0, "production_writes": 0, "deployments": 0, "calibration_ledger_writes": 0, "holdout_test_accessed": False, "production_status": "BASELINE_PRIOR"},
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "independent_rows": len(rows), "fixtures": payload["manifest"]["fixtures"], "cells": len(cells), "training_metrics": payload["training_metrics"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
