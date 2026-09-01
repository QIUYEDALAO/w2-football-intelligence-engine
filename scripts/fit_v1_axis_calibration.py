#!/usr/bin/env python3
"""Fit and score the preregistered V1 AH/TOTALS axis calibration family."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import deque
from collections.abc import Callable
from pathlib import Path
from statistics import mean
from typing import Any

CURRENT = (0.5, 0.5)
AH_BOUNDS = ((0.0, 1.5), (0.0, 1.5))
TOTALS_BOUNDS = ((0.0, 1.5), (0.0, 1.5))
AH_LINES = (-1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5)
TOTALS_LINES = (1.5, 2.5, 3.5)
WARMUP = 1500
FOLDS = 10
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20260901


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mean(values: deque[tuple[float, float]]) -> tuple[float, float]:
    return (
        sum(row[0] for row in values) / len(values),
        sum(row[1] for row in values) / len(values),
    )


def load_rows(home_away_path: Path, xg_path: Path) -> list[dict[str, Any]]:
    home_away = {
        row["fixture_id"]: row
        for row in csv.DictReader(home_away_path.open(newline="", encoding="utf-8"))
    }
    matches: dict[str, dict[str, dict[str, str]]] = {}
    for row in csv.DictReader(xg_path.open(newline="", encoding="utf-8")):
        matches.setdefault(row["fixture_id"], {})[row["team_id"]] = row
    history: dict[str, deque[tuple[float, float]]] = {}
    result: list[dict[str, Any]] = []
    for fixture_id, teams in sorted(
        matches.items(),
        key=lambda item: (min(row["kickoff_at"] for row in item[1].values()), item[0]),
    ):
        identity = home_away.get(fixture_id)
        if identity is None:
            continue
        home = teams.get(identity["home_id"])
        away = teams.get(identity["away_id"])
        if home is None or away is None:
            continue
        home_history = history.setdefault(identity["home_id"], deque(maxlen=5))
        away_history = history.setdefault(identity["away_id"], deque(maxlen=5))
        if len(home_history) == 5 and len(away_history) == 5:
            home_for, home_against = _mean(home_history)
            away_for, away_against = _mean(away_history)
            result.append(
                {
                    "fixture_id": fixture_id,
                    "kickoff_at": home["kickoff_at"],
                    "home_for": home_for,
                    "home_against": home_against,
                    "away_for": away_for,
                    "away_against": away_against,
                    "goals_home": int(home["goals_for"]),
                    "goals_away": int(home["goals_against"]),
                }
            )
        home_history.append((float(home["xg_for"]), float(home["xg_against"])))
        away_history.append((float(away["xg_for"]), float(away["xg_against"])))
    if len(result) != 8659:
        raise ValueError(f"expected frozen eligible fixture count 8659, got {len(result)}")
    return result


def _lambdas(
    row: dict[str, Any],
    ah: tuple[float, float] = CURRENT,
    totals: tuple[float, float] = CURRENT,
) -> tuple[float, float]:
    total = totals[0] * (row["home_for"] + row["away_for"]) + totals[1] * (
        row["home_against"] + row["away_against"]
    )
    total = min(max(total, 1.35), 4.40)
    delta = (
        0.30
        + ah[0] * (row["home_for"] - row["away_for"])
        + ah[1] * (row["away_against"] - row["home_against"])
    )
    return (
        min(max((total + delta) / 2.0, 0.15), 4.25),
        min(max((total - delta) / 2.0, 0.15), 4.25),
    )


def _joint_nll(row: dict[str, Any], ah: tuple[float, float], totals: tuple[float, float]) -> float:
    home, away = _lambdas(row, ah, totals)
    return (
        home
        - row["goals_home"] * math.log(home)
        + math.lgamma(row["goals_home"] + 1)
        + away
        - row["goals_away"] * math.log(away)
        + math.lgamma(row["goals_away"] + 1)
    )


def _total_nll(row: dict[str, Any], ah: tuple[float, float], totals: tuple[float, float]) -> float:
    home, away = _lambdas(row, ah, totals)
    value = home + away
    observed = row["goals_home"] + row["goals_away"]
    return value - observed * math.log(value) + math.lgamma(observed + 1)


def _golden(function: Callable[[float], float], low: float, high: float) -> float:
    phi = (1.0 + math.sqrt(5.0)) / 2.0
    left, right = low, high
    c = right - (right - left) / phi
    d = left + (right - left) / phi
    fc, fd = function(c), function(d)
    while right - left > 1e-6:
        if fc <= fd:
            right, d, fd = d, c, fc
            c = right - (right - left) / phi
            fc = function(c)
        else:
            left, c, fc = c, d, fd
            d = left + (right - left) / phi
            fd = function(d)
    return (left + right) / 2.0


def fit_axis(rows: list[dict[str, Any]], axis: str) -> tuple[float, float]:
    pair = [*CURRENT]
    bounds = AH_BOUNDS if axis == "AH" else TOTALS_BOUNDS

    def objective(candidate: tuple[float, float]) -> float:
        ah = candidate if axis == "AH" else CURRENT
        totals = candidate if axis == "TOTALS" else CURRENT
        return sum(_joint_nll(row, ah, totals) for row in rows)

    for _ in range(50):
        previous = tuple(pair)
        pair[0] = _golden(lambda value: objective((value, pair[1])), *bounds[0])
        pair[1] = _golden(lambda value: objective((pair[0], value)), *bounds[1])
        if max(abs(pair[index] - previous[index]) for index in (0, 1)) <= 1e-6:
            break
    return round(pair[0], 6), round(pair[1], 6)


def _regression(x: list[float], y: list[float]) -> dict[str, float]:
    mean_x, mean_y = mean(x), mean(y)
    denominator = sum((value - mean_x) ** 2 for value in x)
    slope = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y, strict=True)) / denominator
    return {"slope": round(slope, 6), "intercept": round(mean_y - slope * mean_x, 6)}


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _paired_bootstrap(values: list[float], seed_offset: int) -> dict[str, float | int]:
    rng = random.Random(BOOTSTRAP_SEED + seed_offset)  # noqa: S311
    size = len(values)
    estimates = [
        sum(values[rng.randrange(size)] for _ in range(size)) / size
        for _ in range(BOOTSTRAP_RESAMPLES)
    ]
    return {
        "resamples": BOOTSTRAP_RESAMPLES,
        "seed": BOOTSTRAP_SEED + seed_offset,
        "mean": round(mean(values), 9),
        "lower_95": round(_percentile(estimates, 0.025), 9),
        "upper_95": round(_percentile(estimates, 0.975), 9),
    }


def _poisson_probabilities(value: float, maximum: int = 12) -> list[float]:
    values = [math.exp(-value)]
    for goals in range(1, maximum + 1):
        values.append(values[-1] * value / goals)
    return values


def _brier(
    rows: list[dict[str, Any]],
    parameters: list[tuple[tuple[float, float], tuple[float, float]]],
) -> dict[str, Any]:
    ah_errors = {line: [] for line in AH_LINES}
    totals_errors = {line: [] for line in TOTALS_LINES}
    for row, (ah, totals) in zip(rows, parameters, strict=True):
        home_lambda, away_lambda = _lambdas(row, ah, totals)
        home_probabilities = _poisson_probabilities(home_lambda)
        away_probabilities = _poisson_probabilities(away_lambda)
        normalizer = sum(home_probabilities) * sum(away_probabilities)
        margin_probabilities: dict[int, float] = {}
        total_probabilities: dict[int, float] = {}
        for home, home_probability in enumerate(home_probabilities):
            for away, away_probability in enumerate(away_probabilities):
                probability = home_probability * away_probability / normalizer
                margin_probabilities[home - away] = (
                    margin_probabilities.get(home - away, 0.0) + probability
                )
                total_probabilities[home + away] = (
                    total_probabilities.get(home + away, 0.0) + probability
                )
        observed_margin = row["goals_home"] - row["goals_away"]
        observed_total = row["goals_home"] + row["goals_away"]
        for line in AH_LINES:
            predicted = sum(
                probability * (1.0 if margin + line > 0 else 0.5 if margin + line == 0 else 0.0)
                for margin, probability in margin_probabilities.items()
            )
            actual = (
                1.0 if observed_margin + line > 0 else 0.5 if observed_margin + line == 0 else 0.0
            )
            ah_errors[line].append((predicted - actual) ** 2)
        for line in TOTALS_LINES:
            predicted = sum(
                probability for total, probability in total_probabilities.items() if total > line
            )
            actual = float(observed_total > line)
            totals_errors[line].append((predicted - actual) ** 2)
    ah = {str(line): round(mean(values), 9) for line, values in ah_errors.items()}
    totals = {str(line): round(mean(values), 9) for line, values in totals_errors.items()}
    return {
        "AH": {"by_line": ah, "mean": round(mean(ah.values()), 9)},
        "TOTALS": {"by_line": totals, "mean": round(mean(totals.values()), 9)},
    }


def rolling_origin(rows: list[dict[str, Any]]) -> dict[str, Any]:
    remaining = len(rows) - WARMUP
    base, extra = divmod(remaining, FOLDS)
    start = WARMUP
    oof_rows: list[dict[str, Any]] = []
    parameter_rows: dict[str, list[tuple[tuple[float, float], tuple[float, float]]]] = {
        name: [] for name in ("current", "AH", "TOTALS", "combined")
    }
    nll: dict[str, list[float]] = {name: [] for name in parameter_rows}
    total_nll: dict[str, list[float]] = {name: [] for name in parameter_rows}
    folds: list[dict[str, Any]] = []
    for index in range(FOLDS):
        size = base + (1 if index < extra else 0)
        stop = start + size
        ah = fit_axis(rows[:start], "AH")
        totals = fit_axis(rows[:start], "TOTALS")
        fold = rows[start:stop]
        modes = {
            "current": (CURRENT, CURRENT),
            "AH": (ah, CURRENT),
            "TOTALS": (CURRENT, totals),
            "combined": (ah, totals),
        }
        fold_metrics: dict[str, Any] = {}
        for name, parameters in modes.items():
            joint_values = [_joint_nll(row, *parameters) for row in fold]
            total_values = [_total_nll(row, *parameters) for row in fold]
            nll[name].extend(joint_values)
            total_nll[name].extend(total_values)
            parameter_rows[name].extend([parameters] * len(fold))
            fold_metrics[name] = {
                "mean_scoreline_nll": round(mean(joint_values), 9),
                "mean_total_nll": round(mean(total_values), 9),
            }
        folds.append(
            {
                "fold": index + 1,
                "train_count": start,
                "validation_count": size,
                "validation_kickoff_start": fold[0]["kickoff_at"],
                "validation_kickoff_end": fold[-1]["kickoff_at"],
                "ah_parameters": ah,
                "totals_parameters": totals,
                "metrics": fold_metrics,
            }
        )
        oof_rows.extend(fold)
        start = stop
    predictions: dict[str, Any] = {}
    for name, parameters in parameter_rows.items():
        lambdas = [_lambdas(row, *pair) for row, pair in zip(oof_rows, parameters, strict=True)]
        predictions[name] = {
            "margin_regression": _regression(
                [home - away for home, away in lambdas],
                [row["goals_home"] - row["goals_away"] for row in oof_rows],
            ),
            "total_regression": _regression(
                [home + away for home, away in lambdas],
                [row["goals_home"] + row["goals_away"] for row in oof_rows],
            ),
            "mean_total_bias": round(
                mean(
                    home + away - row["goals_home"] - row["goals_away"]
                    for row, (home, away) in zip(oof_rows, lambdas, strict=True)
                ),
                9,
            ),
            "brier": _brier(oof_rows, parameters),
            "mean_scoreline_nll": round(mean(nll[name]), 9),
            "mean_total_nll": round(mean(total_nll[name]), 9),
        }
    differences = {
        "AH_scoreline": [
            candidate - current
            for current, candidate in zip(nll["current"], nll["AH"], strict=True)
        ],
        "TOTALS_total": [
            candidate - current
            for current, candidate in zip(total_nll["current"], total_nll["TOTALS"], strict=True)
        ],
        "combined_scoreline": [
            candidate - current
            for current, candidate in zip(nll["current"], nll["combined"], strict=True)
        ],
    }
    paired = {
        name: _paired_bootstrap(values, offset)
        for offset, (name, values) in enumerate(differences.items())
    }
    ah_improved_folds = sum(
        fold["metrics"]["AH"]["mean_scoreline_nll"]
        < fold["metrics"]["current"]["mean_scoreline_nll"]
        for fold in folds
    )
    totals_improved_folds = sum(
        fold["metrics"]["TOTALS"]["mean_total_nll"] < fold["metrics"]["current"]["mean_total_nll"]
        for fold in folds
    )
    current_ah = predictions["current"]["brier"]["AH"]
    candidate_ah = predictions["AH"]["brier"]["AH"]
    current_totals = predictions["current"]["brier"]["TOTALS"]
    candidate_totals = predictions["TOTALS"]["brier"]["TOTALS"]
    ah_line_improvements = sum(
        candidate_ah["by_line"][str(line)] < current_ah["by_line"][str(line)] for line in AH_LINES
    )
    totals_line_improvements = sum(
        candidate_totals["by_line"][str(line)] < current_totals["by_line"][str(line)]
        for line in TOTALS_LINES
    )
    current_margin = predictions["current"]["margin_regression"]
    candidate_margin = predictions["AH"]["margin_regression"]
    current_total = predictions["current"]["total_regression"]
    candidate_total = predictions["TOTALS"]["total_regression"]
    ah_checks = {
        "paired_scoreline_nll_mean_lt_zero": paired["AH_scoreline"]["mean"] < 0,
        "paired_scoreline_nll_upper_95_le_zero": paired["AH_scoreline"]["upper_95"] <= 0,
        "minimum_7_folds_improve": ah_improved_folds >= 7,
        "margin_slope_closer_to_one": abs(candidate_margin["slope"] - 1)
        < abs(current_margin["slope"] - 1),
        "absolute_margin_intercept_le_0_10": abs(candidate_margin["intercept"]) <= 0.10,
        "mean_generic_ah_brier_lower": candidate_ah["mean"] < current_ah["mean"],
        "minimum_5_generic_lines_improve": ah_line_improvements >= 5,
    }
    totals_checks = {
        "paired_total_nll_mean_lt_zero": paired["TOTALS_total"]["mean"] < 0,
        "paired_total_nll_upper_95_le_zero": paired["TOTALS_total"]["upper_95"] <= 0,
        "minimum_7_folds_improve": totals_improved_folds >= 7,
        "total_slope_closer_to_one": abs(candidate_total["slope"] - 1)
        < abs(current_total["slope"] - 1),
        "absolute_mean_total_bias_le_0_10": abs(predictions["TOTALS"]["mean_total_bias"]) <= 0.10,
        "mean_generic_totals_brier_lower": candidate_totals["mean"] < current_totals["mean"],
        "minimum_2_generic_lines_improve": totals_line_improvements >= 2,
    }
    ah_gain = -paired["AH_scoreline"]["mean"]
    totals_scoreline_gain = (
        predictions["current"]["mean_scoreline_nll"] - predictions["TOTALS"]["mean_scoreline_nll"]
    )
    combined_gain = -paired["combined_scoreline"]["mean"]
    summed_gain = ah_gain + totals_scoreline_gain
    interaction_loss_fraction = (
        (summed_gain - combined_gain) / summed_gain if summed_gain > 0 else math.inf
    )
    combined_checks = {
        "ah_axis_passes": all(ah_checks.values()),
        "totals_axis_passes": all(totals_checks.values()),
        "paired_scoreline_nll_upper_95_le_zero": paired["combined_scoreline"]["upper_95"] <= 0,
        "interaction_loss_fraction_le_0_10": interaction_loss_fraction <= 0.10,
    }
    return {
        "fixture_count": len(oof_rows),
        "folds": folds,
        "folds_improved": {"AH": ah_improved_folds, "TOTALS": totals_improved_folds},
        "generic_lines_improved": {"AH": ah_line_improvements, "TOTALS": totals_line_improvements},
        "predictions": predictions,
        "paired_differences": paired,
        "interaction_loss_fraction": round(interaction_loss_fraction, 9),
        "checks": {"AH": ah_checks, "TOTALS": totals_checks, "combined": combined_checks},
        "passes": {
            "AH": all(ah_checks.values()),
            "TOTALS": all(totals_checks.values()),
            "combined": all(combined_checks.values()),
        },
    }


def build(home_away: Path, xg: Path, protocol: Path) -> dict[str, Any]:
    rows = load_rows(home_away, xg)
    full_ah = fit_axis(rows, "AH")
    full_totals = fit_axis(rows, "TOTALS")
    oof = rolling_origin(rows)
    return {
        "schema": "w2.v1.axis_calibration_fit.v1",
        "sources": {
            "home_away_sha256": _sha256(home_away),
            "xg_sha256": _sha256(xg),
            "protocol_sha256": _sha256(protocol),
        },
        "fixture_count": len(rows),
        "full_development_fit": {
            "AH": {"attack_delta_weight": full_ah[0], "defence_delta_weight": full_ah[1]},
            "TOTALS": {
                "attack_total_weight": full_totals[0],
                "defence_total_weight": full_totals[1],
            },
        },
        "rolling_origin_oof": oof,
        "decision": {
            "AH": "PASS_DEVELOPMENT" if oof["passes"]["AH"] else "REJECTED",
            "TOTALS": "PASS_DEVELOPMENT" if oof["passes"]["TOTALS"] else "REJECTED",
            "combined": "PASS_DEVELOPMENT" if oof["passes"]["combined"] else "REJECTED",
        },
        "safety": {
            "provider_calls": 0,
            "production_reads": 0,
            "production_writes": 0,
            "settled_121_loaded": 0,
            "market_artifact_loaded": 0,
            "ledger_writes": 0,
            "deployment": 0,
        },
    }


def write_report(payload: dict[str, Any], path: Path) -> None:
    oof = payload["rolling_origin_oof"]
    lines = [
        "# V1 AH/TOTALS 轴校准开发验收",
        "",
        f"决策：`{payload['decision']}`。",
        "",
        "本结果只使用严格 PIT 开发/rolling-origin OOF；不构成生产授权或盈利证明。",
        "",
        "## 全开发集拟合值",
        "",
        f"- AH: `{payload['full_development_fit']['AH']}`",
        f"- TOTALS: `{payload['full_development_fit']['TOTALS']}`",
        "",
        "## OOF",
        "",
        f"- fixtures: `{oof['fixture_count']}`",
        f"- folds improved: `{oof['folds_improved']}`",
        f"- generic lines improved: `{oof['generic_lines_improved']}`",
        f"- paired differences: `{oof['paired_differences']}`",
        f"- interaction loss fraction: `{oof['interaction_loss_fraction']}`",
        "",
        "## 冻结门",
        "",
        "```json",
        json.dumps(oof["checks"], indent=2, sort_keys=True),
        "```",
        "",
        "## 边界",
        "",
        "121 注与 259 场市场证据均未由本脚本加载；它们不能选择参数或决定本次通过。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--home-away", type=Path, required=True)
    parser.add_argument("--xg", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    payload = build(args.home_away, args.xg, args.protocol)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(payload, args.report)
    print(json.dumps(payload["decision"], sort_keys=True))


if __name__ == "__main__":
    main()
