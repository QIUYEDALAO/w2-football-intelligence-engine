#!/usr/bin/env python3
"""Fit the preregistered V1 market-axis calibration family."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any

from scripts.fit_v1_axis_calibration import (
    CURRENT,
    FOLDS,
    WARMUP,
    _paired_bootstrap,
    _poisson_probabilities,
    _regression,
    _sha256,
    load_rows,
)

AH_LINES = tuple(value / 4 for value in range(-6, 7))
TOTALS_LINES = (1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5)


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    augmented = [row[:] + [value] for row, value in zip(matrix, vector, strict=True)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("singular least-squares matrix")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                value - factor * reference
                for value, reference in zip(augmented[row], augmented[column], strict=True)
            ]
    return [augmented[row][-1] for row in range(size)]


def _least_squares(features: list[list[float]], outcomes: list[float]) -> tuple[float, ...]:
    columns = len(features[0])
    matrix = [
        [sum(row[left] * row[right] for row in features) for right in range(columns)]
        for left in range(columns)
    ]
    vector = [
        sum(row[column] * outcome for row, outcome in zip(features, outcomes, strict=True))
        for column in range(columns)
    ]
    return tuple(round(value, 6) for value in _solve(matrix, vector))


def fit_ah(rows: list[dict[str, Any]]) -> tuple[float, float, float]:
    features = [
        [
            1.0,
            row["home_for"] - row["away_for"],
            row["away_against"] - row["home_against"],
        ]
        for row in rows
    ]
    outcomes = [row["goals_home"] - row["goals_away"] for row in rows]
    result = _least_squares(features, outcomes)
    bounds = ((0.0, 0.6), (0.0, 1.5), (0.0, 1.5))
    if any(not low <= value <= high for value, (low, high) in zip(result, bounds, strict=True)):
        raise ValueError(f"AH fit outside preregistered bounds: {result}")
    return result


def fit_totals(rows: list[dict[str, Any]]) -> tuple[float, float]:
    features = [
        [
            1.0,
            0.5 * (row["home_for"] + row["away_for"] + row["home_against"] + row["away_against"]),
        ]
        for row in rows
    ]
    outcomes = [row["goals_home"] + row["goals_away"] for row in rows]
    result = _least_squares(features, outcomes)
    bounds = ((-1.0, 1.0), (0.4, 1.2))
    if any(not low <= value <= high for value, (low, high) in zip(result, bounds, strict=True)):
        raise ValueError(f"TOTALS fit outside preregistered bounds: {result}")
    return result


def _lambdas(
    row: dict[str, Any],
    ah: tuple[float, float, float] | None = None,
    totals: tuple[float, float] | None = None,
) -> tuple[float, float, bool]:
    raw_total = 0.5 * (
        row["home_for"] + row["away_for"] + row["home_against"] + row["away_against"]
    )
    total = raw_total if totals is None else totals[0] + totals[1] * raw_total
    total = min(max(total, 1.35), 4.40)
    if ah is None:
        delta = (
            0.30
            + CURRENT[0] * (row["home_for"] - row["away_for"])
            + CURRENT[1] * (row["away_against"] - row["home_against"])
        )
    else:
        delta = (
            ah[0]
            + ah[1] * (row["home_for"] - row["away_for"])
            + ah[2] * (row["away_against"] - row["home_against"])
        )
    raw_home, raw_away = (total + delta) / 2.0, (total - delta) / 2.0
    home = min(max(raw_home, 0.15), 4.25)
    away = min(max(raw_away, 0.15), 4.25)
    return home, away, home != raw_home or away != raw_away


def _joint_nll(row: dict[str, Any], parameters: tuple[Any, Any]) -> float:
    home, away, _ = _lambdas(row, *parameters)
    return (
        home
        - row["goals_home"] * math.log(home)
        + math.lgamma(row["goals_home"] + 1)
        + away
        - row["goals_away"] * math.log(away)
        + math.lgamma(row["goals_away"] + 1)
    )


def _total_nll(row: dict[str, Any], parameters: tuple[Any, Any]) -> float:
    home, away, _ = _lambdas(row, *parameters)
    value = home + away
    observed = row["goals_home"] + row["goals_away"]
    return value - observed * math.log(value) + math.lgamma(observed + 1)


def _single_effective(value: float) -> float:
    return 1.0 if value > 0 else 0.5 if value == 0 else 0.0


def _effective_score(observed: int, line: float) -> float:
    quarter = round(line * 4)
    if quarter % 2 == 0:
        return _single_effective(observed + line)
    return mean(
        (
            _single_effective(observed + line - 0.25),
            _single_effective(observed + line + 0.25),
        )
    )


def _distributions(
    home_lambda: float, away_lambda: float
) -> tuple[dict[int, float], dict[int, float]]:
    home_probabilities = _poisson_probabilities(home_lambda)
    away_probabilities = _poisson_probabilities(away_lambda)
    normalizer = sum(home_probabilities) * sum(away_probabilities)
    margins: dict[int, float] = {}
    totals: dict[int, float] = {}
    for home, home_probability in enumerate(home_probabilities):
        for away, away_probability in enumerate(away_probabilities):
            probability = home_probability * away_probability / normalizer
            margins[home - away] = margins.get(home - away, 0.0) + probability
            totals[home + away] = totals.get(home + away, 0.0) + probability
    return margins, totals


def _fixture_scores(row: dict[str, Any], parameters: tuple[Any, Any]) -> tuple[float, float]:
    home, away, _ = _lambdas(row, *parameters)
    margins, totals = _distributions(home, away)
    observed_margin = row["goals_home"] - row["goals_away"]
    observed_total = row["goals_home"] + row["goals_away"]
    ah_errors = []
    for line in AH_LINES:
        predicted = sum(
            probability * _effective_score(margin, line) for margin, probability in margins.items()
        )
        actual = _effective_score(observed_margin, line)
        ah_errors.append((predicted - actual) ** 2)
    totals_errors = []
    for line in TOTALS_LINES:
        predicted = sum(
            probability * _effective_score(total, -line) for total, probability in totals.items()
        )
        actual = _effective_score(observed_total, -line)
        totals_errors.append((predicted - actual) ** 2)
    return mean(ah_errors), mean(totals_errors)


def rolling_origin(rows: list[dict[str, Any]]) -> dict[str, Any]:
    remaining = len(rows) - WARMUP
    base, extra = divmod(remaining, FOLDS)
    start = WARMUP
    oof_rows: list[dict[str, Any]] = []
    parameters: dict[str, list[tuple[Any, Any]]] = {
        name: [] for name in ("current", "AH", "TOTALS", "combined")
    }
    folds: list[dict[str, Any]] = []
    for index in range(FOLDS):
        size = base + (1 if index < extra else 0)
        stop = start + size
        ah = fit_ah(rows[:start])
        totals = fit_totals(rows[:start])
        fold = rows[start:stop]
        modes = {
            "current": (None, None),
            "AH": (ah, None),
            "TOTALS": (None, totals),
            "combined": (ah, totals),
        }
        for name, pair in modes.items():
            parameters[name].extend([pair] * len(fold))
        folds.append(
            {
                "fold": index + 1,
                "train_count": start,
                "validation_count": size,
                "validation_kickoff_start": fold[0]["kickoff_at"],
                "validation_kickoff_end": fold[-1]["kickoff_at"],
                "ah_parameters": ah,
                "totals_parameters": totals,
            }
        )
        oof_rows.extend(fold)
        start = stop

    metrics: dict[str, Any] = {}
    fixture_scores: dict[str, list[tuple[float, float]]] = {}
    joint_nll: dict[str, list[float]] = {}
    total_nll: dict[str, list[float]] = {}
    for name, mode_parameters in parameters.items():
        lambdas = [
            _lambdas(row, *pair) for row, pair in zip(oof_rows, mode_parameters, strict=True)
        ]
        fixture_scores[name] = [
            _fixture_scores(row, pair) for row, pair in zip(oof_rows, mode_parameters, strict=True)
        ]
        joint_nll[name] = [
            _joint_nll(row, pair) for row, pair in zip(oof_rows, mode_parameters, strict=True)
        ]
        total_nll[name] = [
            _total_nll(row, pair) for row, pair in zip(oof_rows, mode_parameters, strict=True)
        ]
        metrics[name] = {
            "mean_ah_brier": round(mean(value[0] for value in fixture_scores[name]), 9),
            "mean_totals_brier": round(mean(value[1] for value in fixture_scores[name]), 9),
            "mean_scoreline_nll": round(mean(joint_nll[name]), 9),
            "mean_total_nll": round(mean(total_nll[name]), 9),
            "margin_regression": _regression(
                [home - away for home, away, _ in lambdas],
                [row["goals_home"] - row["goals_away"] for row in oof_rows],
            ),
            "total_regression": _regression(
                [home + away for home, away, _ in lambdas],
                [row["goals_home"] + row["goals_away"] for row in oof_rows],
            ),
            "mean_total_bias": round(
                mean(
                    home + away - row["goals_home"] - row["goals_away"]
                    for row, (home, away, _) in zip(oof_rows, lambdas, strict=True)
                ),
                9,
            ),
            "lambda_clamp_count": sum(clamped for _, _, clamped in lambdas),
        }

    differences = {
        "AH_brier": [
            candidate[0] - current[0]
            for current, candidate in zip(
                fixture_scores["current"], fixture_scores["AH"], strict=True
            )
        ],
        "AH_scoreline_nll": [
            candidate - current
            for current, candidate in zip(joint_nll["current"], joint_nll["AH"], strict=True)
        ],
        "TOTALS_brier": [
            candidate[1] - current[1]
            for current, candidate in zip(
                fixture_scores["current"], fixture_scores["TOTALS"], strict=True
            )
        ],
        "TOTALS_nll": [
            candidate - current
            for current, candidate in zip(total_nll["current"], total_nll["TOTALS"], strict=True)
        ],
        "combined_scoreline_nll": [
            candidate - current
            for current, candidate in zip(joint_nll["current"], joint_nll["combined"], strict=True)
        ],
    }
    paired = {
        name: _paired_bootstrap(values, index)
        for index, (name, values) in enumerate(differences.items())
    }

    fold_ranges = []
    cursor = 0
    for fold in folds:
        stop = cursor + fold["validation_count"]
        fold_ranges.append((cursor, stop))
        cursor = stop
    ah_folds = sum(
        mean(value[0] for value in fixture_scores["AH"][left:right])
        < mean(value[0] for value in fixture_scores["current"][left:right])
        for left, right in fold_ranges
    )
    totals_folds = sum(
        mean(value[1] for value in fixture_scores["TOTALS"][left:right])
        < mean(value[1] for value in fixture_scores["current"][left:right])
        for left, right in fold_ranges
    )

    def line_brier(name: str, market: str, line: float) -> float:
        errors = []
        for row, pair in zip(oof_rows, parameters[name], strict=True):
            home, away, _ = _lambdas(row, *pair)
            margins, totals = _distributions(home, away)
            distribution = margins if market == "AH" else totals
            observed = (
                row["goals_home"] - row["goals_away"]
                if market == "AH"
                else row["goals_home"] + row["goals_away"]
            )
            applied_line = line if market == "AH" else -line
            predicted = sum(
                probability * _effective_score(value, applied_line)
                for value, probability in distribution.items()
            )
            errors.append((predicted - _effective_score(observed, applied_line)) ** 2)
        return mean(errors)

    ah_lines = {
        str(line): {name: round(line_brier(name, "AH", line), 9) for name in ("current", "AH")}
        for line in AH_LINES
    }
    totals_lines = {
        str(line): {
            name: round(line_brier(name, "TOTALS", line), 9) for name in ("current", "TOTALS")
        }
        for line in TOTALS_LINES
    }
    ah_line_count = sum(values["AH"] < values["current"] for values in ah_lines.values())
    totals_line_count = sum(
        values["TOTALS"] < values["current"] for values in totals_lines.values()
    )
    current_margin = metrics["current"]["margin_regression"]
    candidate_margin = metrics["AH"]["margin_regression"]
    current_total = metrics["current"]["total_regression"]
    candidate_total = metrics["TOTALS"]["total_regression"]
    ah_checks = {
        "brier_upper_95_le_zero": paired["AH_brier"]["upper_95"] <= 0,
        "minimum_7_folds_improve": ah_folds >= 7,
        "minimum_10_lines_improve": ah_line_count >= 10,
        "margin_slope_closer_to_one": abs(candidate_margin["slope"] - 1)
        < abs(current_margin["slope"] - 1),
        "absolute_margin_intercept_le_0_10": abs(candidate_margin["intercept"]) <= 0.1,
        "scoreline_nll_noninferiority_upper_95_le_0_001": paired["AH_scoreline_nll"]["upper_95"]
        <= 0.001,
    }
    totals_checks = {
        "brier_upper_95_le_zero": paired["TOTALS_brier"]["upper_95"] <= 0,
        "total_nll_upper_95_le_zero": paired["TOTALS_nll"]["upper_95"] <= 0,
        "minimum_7_folds_improve": totals_folds >= 7,
        "minimum_5_lines_improve": totals_line_count >= 5,
        "total_slope_closer_to_one": abs(candidate_total["slope"] - 1)
        < abs(current_total["slope"] - 1),
        "absolute_mean_total_bias_le_0_10": abs(metrics["TOTALS"]["mean_total_bias"]) <= 0.1,
    }
    combined_checks = {
        "ah_passes": all(ah_checks.values()),
        "totals_passes": all(totals_checks.values()),
        "scoreline_nll_upper_95_le_zero": paired["combined_scoreline_nll"]["upper_95"] <= 0,
    }
    return {
        "fixture_count": len(oof_rows),
        "folds": folds,
        "metrics": metrics,
        "paired_differences": paired,
        "folds_improved": {"AH": ah_folds, "TOTALS": totals_folds},
        "line_brier": {"AH": ah_lines, "TOTALS": totals_lines},
        "lines_improved": {"AH": ah_line_count, "TOTALS": totals_line_count},
        "checks": {"AH": ah_checks, "TOTALS": totals_checks, "combined": combined_checks},
        "passes": {
            "AH": all(ah_checks.values()),
            "TOTALS": all(totals_checks.values()),
            "combined": all(combined_checks.values()),
        },
    }


def build(home_away: Path, xg: Path, protocol: Path) -> dict[str, Any]:
    rows = load_rows(home_away, xg)
    full_ah = fit_ah(rows)
    full_totals = fit_totals(rows)
    oof = rolling_origin(rows)
    return {
        "schema": "w2.v1.market_axis_calibration_fit.v1",
        "sources": {
            "home_away_sha256": _sha256(home_away),
            "xg_sha256": _sha256(xg),
            "protocol_sha256": _sha256(protocol),
        },
        "fixture_count": len(rows),
        "full_development_fit": {
            "AH": {
                "home_intercept": full_ah[0],
                "attack_weight": full_ah[1],
                "defence_weight": full_ah[2],
            },
            "TOTALS": {"total_intercept": full_totals[0], "total_scale": full_totals[1]},
        },
        "rolling_origin_oof": oof,
        "decision": {
            name: "PASS_DEVELOPMENT" if passed else "REJECTED"
            for name, passed in oof["passes"].items()
        },
        "safety": {
            "provider_calls": 0,
            "production_reads": 0,
            "production_writes": 0,
            "settled_121_loaded": 0,
            "market_259_loaded": 0,
            "ledger_writes": 0,
            "deployment": 0,
        },
    }


def write_report(payload: dict[str, Any], path: Path) -> None:
    oof = payload["rolling_origin_oof"]
    lines = [
        "# V1 市场轴校准开发验收",
        "",
        f"决策：`{payload['decision']}`。",
        "",
        "严格 PIT/rolling-origin OOF 开发证据；不构成生产授权、盈利证明或 ledger grant。",
        "",
        "## 拟合值",
        "",
        f"- AH: `{payload['full_development_fit']['AH']}`",
        f"- TOTALS: `{payload['full_development_fit']['TOTALS']}`",
        "",
        "## OOF",
        "",
        f"- fixtures: `{oof['fixture_count']}`",
        f"- folds improved: `{oof['folds_improved']}`",
        f"- lines improved: `{oof['lines_improved']}`",
        f"- paired differences: `{oof['paired_differences']}`",
        "",
        "## 冻结门",
        "",
        "```json",
        json.dumps(oof["checks"], indent=2, sort_keys=True),
        "```",
        "",
        "121 注与 259 场市场 artifact 均未加载，不能选择参数或决定通过。",
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
