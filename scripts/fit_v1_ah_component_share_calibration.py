#!/usr/bin/env python3
"""Fit and score the final preregistered V1 AH component-share family."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from statistics import mean
from typing import Any

from scripts.fit_v1_ah_goal_share_calibration import (
    _ah_errors,
    _current_delta,
    _current_logit,
    _fixed_total,
    _joint_nll,
    _percentile,
    _sigmoid,
    _softplus,
    _total_nll,
    _validate_frozen_sources,
)
from scripts.fit_v1_ah_goal_share_calibration import (
    _lambdas as _baseline_lambdas,
)
from scripts.fit_v1_axis_calibration import FOLDS, WARMUP, _regression, load_rows
from scripts.fit_v1_market_axis_calibration import AH_LINES, _solve

BOOTSTRAP_RESAMPLES = 8000
BOOTSTRAP_SEED_BASE = 20260921
BOOTSTRAP_LOWER_PROBABILITY = 0.00625
BOOTSTRAP_UPPER_PROBABILITY = 0.99375
PARAMETER_BOUNDS = ((-1.0, 2.0),) * 3


def _features(row: dict[str, Any]) -> tuple[float, float, float]:
    total = _fixed_total(row)
    return (
        0.30 / total,
        0.5 * (row["home_for"] - row["away_for"]) / total,
        0.5 * (row["away_against"] - row["home_against"]) / total,
    )


def _eta(row: dict[str, Any], parameters: tuple[float, float, float]) -> float:
    return _current_logit(row) + sum(
        parameter * feature for parameter, feature in zip(parameters, _features(row), strict=True)
    )


def _objective(rows: list[dict[str, Any]], parameters: tuple[float, float, float]) -> float:
    return sum(
        (row["goals_home"] + row["goals_away"]) * _softplus(_eta(row, parameters))
        - row["goals_home"] * _eta(row, parameters)
        for row in rows
    )


def fit(rows: list[dict[str, Any]]) -> tuple[float, float, float]:
    parameters = [0.0, 0.0, 0.0]
    for _ in range(100):
        gradient = [0.0, 0.0, 0.0]
        hessian = [[0.0] * 3 for _ in range(3)]
        for row in rows:
            features = _features(row)
            probability = _sigmoid(_eta(row, tuple(parameters)))
            total_goals = row["goals_home"] + row["goals_away"]
            residual = total_goals * probability - row["goals_home"]
            weight = total_goals * probability * (1.0 - probability)
            for left in range(3):
                gradient[left] += residual * features[left]
                for right in range(3):
                    hessian[left][right] += weight * features[left] * features[right]
        if max(abs(value) for value in gradient) <= 1e-10:
            break
        step = _solve(hessian, gradient)
        updated = [parameters[index] - step[index] for index in range(3)]
        if _objective(rows, tuple(updated)) > _objective(rows, tuple(parameters)) + 1e-9:
            raise ValueError("component-share Newton step increased the frozen objective")
        change = max(abs(updated[index] - parameters[index]) for index in range(3))
        parameters = updated
        if change <= 1e-12:
            break
    else:
        raise ValueError("component-share Newton optimizer did not converge")
    if any(
        not low <= value <= high
        for value, (low, high) in zip(parameters, PARAMETER_BOUNDS, strict=True)
    ):
        raise ValueError(f"component-share fit outside preregistered bounds: {parameters}")
    return (
        round(parameters[0], 6),
        round(parameters[1], 6),
        round(parameters[2], 6),
    )


def _raw_current_share(row: dict[str, Any]) -> float:
    total = _fixed_total(row)
    return (total + _current_delta(row)) / (2.0 * total)


def _lambdas(
    row: dict[str, Any],
    arm: str,
    parameters: tuple[float, float, float] | None = None,
) -> tuple[float, float, bool]:
    if arm != "candidate":
        return _baseline_lambdas(row, arm)
    if parameters is None:
        raise ValueError("candidate component-share parameters are required")
    total = _fixed_total(row)
    share = _sigmoid(_eta(row, parameters))
    home, away = total * share, total * (1.0 - share)
    clamped = not (0.15 <= home <= 4.25 and 0.15 <= away <= 4.25)
    return home, away, clamped


def _paired_bootstrap(values: list[float], seed_offset: int) -> dict[str, float | int]:
    rng = random.Random(BOOTSTRAP_SEED_BASE + seed_offset)  # noqa: S311
    size = len(values)
    estimates = [
        sum(values[rng.randrange(size)] for _ in range(size)) / size
        for _ in range(BOOTSTRAP_RESAMPLES)
    ]
    return {
        "resamples": BOOTSTRAP_RESAMPLES,
        "seed": BOOTSTRAP_SEED_BASE + seed_offset,
        "mean": round(mean(values), 9),
        "lower_99_375": round(_percentile(estimates, BOOTSTRAP_LOWER_PROBABILITY), 9),
        "upper_99_375": round(_percentile(estimates, BOOTSTRAP_UPPER_PROBABILITY), 9),
    }


def rolling_origin(rows: list[dict[str, Any]]) -> dict[str, Any]:
    remaining = len(rows) - WARMUP
    base, extra = divmod(remaining, FOLDS)
    start = WARMUP
    cursor = 0
    oof_rows: list[dict[str, Any]] = []
    candidate_parameters: list[tuple[float, float, float]] = []
    folds: list[dict[str, Any]] = []
    fold_ranges: list[tuple[int, int]] = []
    for index in range(FOLDS):
        size = base + (1 if index < extra else 0)
        stop = start + size
        parameters = fit(rows[:start])
        fold = rows[start:stop]
        oof_rows.extend(fold)
        candidate_parameters.extend([parameters] * size)
        fold_ranges.append((cursor, cursor + size))
        cursor += size
        folds.append(
            {
                "fold": index + 1,
                "train_count": start,
                "validation_count": size,
                "validation_kickoff_start": fold[0]["kickoff_at"],
                "validation_kickoff_end": fold[-1]["kickoff_at"],
                "home_adjustment": parameters[0],
                "attack_adjustment": parameters[1],
                "defence_adjustment": parameters[2],
            }
        )
        start = stop

    arms: dict[str, dict[str, Any]] = {}
    for arm in ("production_current", "totals_only", "candidate"):
        lambdas = [
            _lambdas(
                row,
                arm,
                candidate_parameters[index] if arm == "candidate" else None,
            )
            for index, row in enumerate(oof_rows)
        ]
        ah_errors = [_ah_errors(row, value) for row, value in zip(oof_rows, lambdas, strict=True)]
        joint_nll = [_joint_nll(row, value) for row, value in zip(oof_rows, lambdas, strict=True)]
        total_nll = [_total_nll(row, value) for row, value in zip(oof_rows, lambdas, strict=True)]
        arms[arm] = {
            "lambdas": lambdas,
            "fixture_ah_brier": [mean(values.values()) for values in ah_errors],
            "line_ah_brier": {
                str(line): round(mean(values[line] for values in ah_errors), 9) for line in AH_LINES
            },
            "joint_nll": joint_nll,
            "total_nll": total_nll,
            "metrics": {
                "mean_ah_brier": round(mean(mean(values.values()) for values in ah_errors), 9),
                "mean_scoreline_nll": round(mean(joint_nll), 9),
                "mean_total_nll": round(mean(total_nll), 9),
                "margin_regression": _regression(
                    [home - away for home, away, _ in lambdas],
                    [row["goals_home"] - row["goals_away"] for row in oof_rows],
                ),
                "lambda_clamp_count": sum(value[2] for value in lambdas),
            },
        }

    differences = {
        "ah_brier_vs_totals_only": [
            candidate - baseline
            for candidate, baseline in zip(
                arms["candidate"]["fixture_ah_brier"],
                arms["totals_only"]["fixture_ah_brier"],
                strict=True,
            )
        ],
        "scoreline_nll_vs_totals_only": [
            candidate - baseline
            for candidate, baseline in zip(
                arms["candidate"]["joint_nll"],
                arms["totals_only"]["joint_nll"],
                strict=True,
            )
        ],
        "ah_brier_vs_production_current": [
            candidate - baseline
            for candidate, baseline in zip(
                arms["candidate"]["fixture_ah_brier"],
                arms["production_current"]["fixture_ah_brier"],
                strict=True,
            )
        ],
        "scoreline_nll_vs_production_current": [
            candidate - baseline
            for candidate, baseline in zip(
                arms["candidate"]["joint_nll"],
                arms["production_current"]["joint_nll"],
                strict=True,
            )
        ],
    }
    paired = {
        name: _paired_bootstrap(values, index)
        for index, (name, values) in enumerate(differences.items())
    }
    folds_improved = sum(
        mean(arms["candidate"]["fixture_ah_brier"][left:right])
        < mean(arms["totals_only"]["fixture_ah_brier"][left:right])
        for left, right in fold_ranges
    )
    lines_improved = sum(
        arms["candidate"]["line_ah_brier"][str(line)]
        < arms["totals_only"]["line_ah_brier"][str(line)]
        for line in AH_LINES
    )
    total_lambda_max_difference = max(
        abs(candidate[0] + candidate[1] - baseline[0] - baseline[1])
        for candidate, baseline in zip(
            arms["candidate"]["lambdas"],
            arms["totals_only"]["lambdas"],
            strict=True,
        )
    )
    total_nll_max_difference = max(
        abs(candidate - baseline)
        for candidate, baseline in zip(
            arms["candidate"]["total_nll"],
            arms["totals_only"]["total_nll"],
            strict=True,
        )
    )
    candidate_margin = arms["candidate"]["metrics"]["margin_regression"]
    baseline_margin = arms["totals_only"]["metrics"]["margin_regression"]
    parameters_inside_bounds = all(
        all(
            low <= fold[name] <= high
            for name, (low, high) in zip(
                ("home_adjustment", "attack_adjustment", "defence_adjustment"),
                PARAMETER_BOUNDS,
                strict=True,
            )
        )
        for fold in folds
    )
    current_share_clamp_count = sum(not 0.0 < _raw_current_share(row) < 1.0 for row in oof_rows)
    checks = {
        "ah_brier_vs_totals_only_upper_99_375_le_zero": paired["ah_brier_vs_totals_only"][
            "upper_99_375"
        ]
        <= 0,
        "scoreline_nll_vs_totals_only_upper_99_375_le_zero": paired["scoreline_nll_vs_totals_only"][
            "upper_99_375"
        ]
        <= 0,
        "ah_brier_vs_production_current_upper_99_375_le_zero": paired[
            "ah_brier_vs_production_current"
        ]["upper_99_375"]
        <= 0,
        "scoreline_nll_vs_production_current_upper_99_375_le_zero": paired[
            "scoreline_nll_vs_production_current"
        ]["upper_99_375"]
        <= 0,
        "minimum_7_folds_improve": folds_improved >= 7,
        "minimum_10_lines_improve": lines_improved >= 10,
        "margin_slope_closer_to_one": abs(candidate_margin["slope"] - 1)
        < abs(baseline_margin["slope"] - 1),
        "absolute_margin_intercept_le_0_10": abs(candidate_margin["intercept"]) <= 0.1,
        "total_lambda_max_difference_le_1e_12": total_lambda_max_difference <= 1e-12,
        "total_nll_max_difference_le_1e_12": total_nll_max_difference <= 1e-12,
        "current_share_clamp_count_zero": current_share_clamp_count == 0,
        "lambda_clamp_count_zero": arms["candidate"]["metrics"]["lambda_clamp_count"] == 0,
        "fitted_parameters_inside_bounds": parameters_inside_bounds,
        "component_monotonicity_proven_by_bounds": parameters_inside_bounds
        and current_share_clamp_count == 0,
    }
    return {
        "fixture_count": len(oof_rows),
        "folds": folds,
        "metrics": {name: value["metrics"] for name, value in arms.items()},
        "line_ah_brier": {name: value["line_ah_brier"] for name, value in arms.items()},
        "paired_differences": paired,
        "folds_improved": folds_improved,
        "lines_improved": lines_improved,
        "current_share_clamp_count": current_share_clamp_count,
        "maximum_absolute_total_lambda_difference_vs_totals_only": round(
            total_lambda_max_difference, 15
        ),
        "maximum_absolute_total_nll_difference_vs_totals_only": round(total_nll_max_difference, 15),
        "checks": checks,
        "passes": all(checks.values()),
    }


def build(home_away: Path, xg: Path, protocol: Path) -> dict[str, Any]:
    sources = _validate_frozen_sources(home_away, xg, protocol)
    rows = load_rows(home_away, xg)
    full_parameters = fit(rows)
    oof = rolling_origin(rows)
    full_inside_bounds = all(
        low <= value <= high
        for value, (low, high) in zip(full_parameters, PARAMETER_BOUNDS, strict=True)
    )
    full_current_share_clamp_count = sum(not 0.0 < _raw_current_share(row) < 1.0 for row in rows)
    oof["checks"]["fitted_parameters_inside_bounds"] = (
        oof["checks"]["fitted_parameters_inside_bounds"] and full_inside_bounds
    )
    oof["checks"]["current_share_clamp_count_zero"] = (
        oof["checks"]["current_share_clamp_count_zero"] and full_current_share_clamp_count == 0
    )
    oof["checks"]["component_monotonicity_proven_by_bounds"] = (
        oof["checks"]["component_monotonicity_proven_by_bounds"]
        and full_inside_bounds
        and full_current_share_clamp_count == 0
    )
    oof["passes"] = all(oof["checks"].values())
    return {
        "schema": "w2.v1.ah_component_share_calibration_fit.v1",
        "sources": sources,
        "fixture_count": len(rows),
        "full_development_fit": {
            "home_adjustment": full_parameters[0],
            "attack_adjustment": full_parameters[1],
            "defence_adjustment": full_parameters[2],
        },
        "full_current_share_clamp_count": full_current_share_clamp_count,
        "rolling_origin_oof": oof,
        "decision": "PASS_DEVELOPMENT" if oof["passes"] else "REJECTED",
        "safety": {
            "provider_calls": 0,
            "production_reads": 0,
            "production_writes": 0,
            "settled_121_loaded": 0,
            "market_259_loaded": 0,
            "raw_delta_scale_used": 0,
            "v2_changes": 0,
            "ledger_writes": 0,
            "deployment": 0,
        },
    }


def write_report(payload: dict[str, Any], path: Path) -> None:
    oof = payload["rolling_origin_oof"]
    margins = {name: values["margin_regression"] for name, values in oof["metrics"].items()}
    lines = [
        "# V1 AH component-share 最终开发验收",
        "",
        f"决策：`{payload['decision']}`。",
        "",
        "同一开发集上的第 4 个且最终 AH 家族；使用 Bonferroni 修正后的 99.375% 上界。",
        "不构成 calibration grant、部署授权、盈利证明或生产有效性证明。",
        "",
        f"- full fit: `{payload['full_development_fit']}`",
        f"- OOF fixtures: `{oof['fixture_count']}`",
        f"- improved folds/lines: `{oof['folds_improved']}/10`, `{oof['lines_improved']}/13`",
        f"- paired differences: `{oof['paired_differences']}`",
        f"- margin regressions: `{margins}`",
        "- total invariance: lambda `"
        f"{oof['maximum_absolute_total_lambda_difference_vs_totals_only']}`, NLL `"
        f"{oof['maximum_absolute_total_nll_difference_vs_totals_only']}`",
        "",
        "## 冻结门",
        "",
        "```json",
        json.dumps(oof["checks"], indent=2, sort_keys=True),
        "```",
        "",
        "121 注与 259 场市场 artifact 均未加载。失败时停止在该开发集上继续搜索 AH 家族。",
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
    print(json.dumps({"decision": payload["decision"]}, sort_keys=True))


if __name__ == "__main__":
    main()
