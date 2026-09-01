#!/usr/bin/env python3
"""Fit and score the preregistered V1 AH conditional goal-share family."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path
from statistics import mean
from typing import Any

from scripts.fit_v1_axis_calibration import FOLDS, WARMUP, _regression, load_rows
from scripts.fit_v1_market_axis_calibration import (
    AH_LINES,
    _distributions,
    _effective_score,
)

TOTAL_INTERCEPT = 0.885958
TOTAL_SCALE = 0.701191
MINIMUM_TOTAL = 1.35
MAXIMUM_TOTAL = 4.40
MINIMUM_LAMBDA = 0.15
MAXIMUM_LAMBDA = 4.25
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED_BASE = 20260911
PARAMETER_BOUNDS = ((-1.0, 1.0), (0.25, 2.0))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_frozen_sources(home_away: Path, xg: Path, protocol: Path) -> dict[str, str]:
    preregistration = json.loads(protocol.read_text(encoding="utf-8"))
    expected = preregistration["data"]["strict_pit_8659"]
    actual = {
        "home_away_sha256": _sha256(home_away),
        "xg_sha256": _sha256(xg),
        "protocol_sha256": _sha256(protocol),
    }
    for name in ("home_away_sha256", "xg_sha256"):
        if actual[name] != expected[name]:
            raise ValueError(
                f"frozen {name} mismatch: expected {expected[name]}, got {actual[name]}"
            )
    return actual


def _fixed_total(row: dict[str, Any]) -> float:
    raw_total = 0.5 * (
        row["home_for"] + row["away_for"] + row["home_against"] + row["away_against"]
    )
    return min(max(TOTAL_INTERCEPT + TOTAL_SCALE * raw_total, MINIMUM_TOTAL), MAXIMUM_TOTAL)


def _current_delta(row: dict[str, Any]) -> float:
    return (
        0.30
        + 0.5 * (row["home_for"] - row["away_for"])
        + 0.5 * (row["away_against"] - row["home_against"])
    )


def _current_logit(row: dict[str, Any]) -> float:
    total = _fixed_total(row)
    share = min(max((total + _current_delta(row)) / (2.0 * total), 1e-9), 1.0 - 1e-9)
    return math.log(share / (1.0 - share))


def _sigmoid(value: float) -> float:
    if value >= 0:
        inverse = math.exp(-value)
        return 1.0 / (1.0 + inverse)
    exponent = math.exp(value)
    return exponent / (1.0 + exponent)


def _softplus(value: float) -> float:
    return value + math.log1p(math.exp(-value)) if value >= 0 else math.log1p(math.exp(value))


def _objective(rows: list[dict[str, Any]], parameters: tuple[float, float]) -> float:
    intercept, scale = parameters
    return sum(
        (row["goals_home"] + row["goals_away"]) * _softplus(intercept + scale * _current_logit(row))
        - row["goals_home"] * (intercept + scale * _current_logit(row))
        for row in rows
    )


def fit(rows: list[dict[str, Any]]) -> tuple[float, float]:
    parameters = [0.0, 1.0]
    for _ in range(100):
        gradient = [0.0, 0.0]
        hessian = [[0.0, 0.0], [0.0, 0.0]]
        for row in rows:
            predictor = _current_logit(row)
            eta = parameters[0] + parameters[1] * predictor
            probability = _sigmoid(eta)
            total_goals = row["goals_home"] + row["goals_away"]
            residual = total_goals * probability - row["goals_home"]
            weight = total_goals * probability * (1.0 - probability)
            gradient[0] += residual
            gradient[1] += residual * predictor
            hessian[0][0] += weight
            hessian[0][1] += weight * predictor
            hessian[1][0] += weight * predictor
            hessian[1][1] += weight * predictor * predictor
        if max(abs(value) for value in gradient) <= 1e-10:
            break
        determinant = hessian[0][0] * hessian[1][1] - hessian[0][1] * hessian[1][0]
        if abs(determinant) < 1e-12:
            raise ValueError("singular goal-share Hessian")
        step = (
            ((hessian[1][1] * gradient[0] - hessian[0][1] * gradient[1]) / determinant),
            ((-hessian[1][0] * gradient[0] + hessian[0][0] * gradient[1]) / determinant),
        )
        updated = [parameters[index] - step[index] for index in range(2)]
        if (
            _objective(rows, (updated[0], updated[1]))
            > _objective(rows, (parameters[0], parameters[1])) + 1e-9
        ):
            raise ValueError("goal-share Newton step increased the frozen objective")
        change = max(abs(updated[index] - parameters[index]) for index in range(2))
        parameters = updated
        if change <= 1e-12:
            break
    else:
        raise ValueError("goal-share Newton optimizer did not converge")
    if any(
        not low <= value <= high
        for value, (low, high) in zip(parameters, PARAMETER_BOUNDS, strict=True)
    ):
        raise ValueError(f"goal-share fit outside preregistered bounds: {tuple(parameters)}")
    result = (round(parameters[0], 6), round(parameters[1], 6))
    if any(
        not low <= value <= high
        for value, (low, high) in zip(result, PARAMETER_BOUNDS, strict=True)
    ):
        raise ValueError(f"goal-share fit outside preregistered bounds: {result}")
    return result


def _lambdas(
    row: dict[str, Any], arm: str, parameters: tuple[float, float] | None = None
) -> tuple[float, float, bool]:
    if arm == "production_current":
        raw_total = 0.5 * (
            row["home_for"] + row["away_for"] + row["home_against"] + row["away_against"]
        )
        total = min(max(raw_total, MINIMUM_TOTAL), MAXIMUM_TOTAL)
        raw_home = (total + _current_delta(row)) / 2.0
        raw_away = (total - _current_delta(row)) / 2.0
        home = min(max(raw_home, MINIMUM_LAMBDA), MAXIMUM_LAMBDA)
        away = min(max(raw_away, MINIMUM_LAMBDA), MAXIMUM_LAMBDA)
        return home, away, home != raw_home or away != raw_away
    total = _fixed_total(row)
    if arm == "totals_only":
        raw_home = (total + _current_delta(row)) / 2.0
        raw_away = (total - _current_delta(row)) / 2.0
        home = min(max(raw_home, MINIMUM_LAMBDA), MAXIMUM_LAMBDA)
        away = min(max(raw_away, MINIMUM_LAMBDA), MAXIMUM_LAMBDA)
        return home, away, home != raw_home or away != raw_away
    if arm != "candidate" or parameters is None:
        raise ValueError(f"unsupported goal-share arm: {arm}")
    share = _sigmoid(parameters[0] + parameters[1] * _current_logit(row))
    home, away = total * share, total * (1.0 - share)
    clamped = not (
        MINIMUM_LAMBDA <= home <= MAXIMUM_LAMBDA and MINIMUM_LAMBDA <= away <= MAXIMUM_LAMBDA
    )
    return home, away, clamped


def _joint_nll(row: dict[str, Any], lambdas: tuple[float, float, bool]) -> float:
    home, away, _ = lambdas
    return (
        home
        - row["goals_home"] * math.log(home)
        + math.lgamma(row["goals_home"] + 1)
        + away
        - row["goals_away"] * math.log(away)
        + math.lgamma(row["goals_away"] + 1)
    )


def _total_nll(row: dict[str, Any], lambdas: tuple[float, float, bool]) -> float:
    home, away, _ = lambdas
    total = home + away
    observed = row["goals_home"] + row["goals_away"]
    return total - observed * math.log(total) + math.lgamma(observed + 1)


def _ah_errors(row: dict[str, Any], lambdas: tuple[float, float, bool]) -> dict[float, float]:
    margins, _ = _distributions(lambdas[0], lambdas[1])
    observed = row["goals_home"] - row["goals_away"]
    return {
        line: (
            sum(
                probability * _effective_score(margin, line)
                for margin, probability in margins.items()
            )
            - _effective_score(observed, line)
        )
        ** 2
        for line in AH_LINES
    }


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


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
        "lower_95": round(_percentile(estimates, 0.025), 9),
        "upper_95": round(_percentile(estimates, 0.975), 9),
    }


def rolling_origin(rows: list[dict[str, Any]]) -> dict[str, Any]:
    remaining = len(rows) - WARMUP
    base, extra = divmod(remaining, FOLDS)
    start = WARMUP
    oof_rows: list[dict[str, Any]] = []
    candidate_parameters: list[tuple[float, float]] = []
    folds: list[dict[str, Any]] = []
    fold_ranges: list[tuple[int, int]] = []
    cursor = 0
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
                "share_intercept": parameters[0],
                "share_logit_scale": parameters[1],
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
                arms["candidate"]["joint_nll"], arms["totals_only"]["joint_nll"], strict=True
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
            arms["candidate"]["lambdas"], arms["totals_only"]["lambdas"], strict=True
        )
    )
    total_nll_max_difference = max(
        abs(candidate - baseline)
        for candidate, baseline in zip(
            arms["candidate"]["total_nll"], arms["totals_only"]["total_nll"], strict=True
        )
    )
    candidate_margin = arms["candidate"]["metrics"]["margin_regression"]
    baseline_margin = arms["totals_only"]["metrics"]["margin_regression"]
    parameters_inside_bounds = all(
        PARAMETER_BOUNDS[0][0] <= row["share_intercept"] <= PARAMETER_BOUNDS[0][1]
        and PARAMETER_BOUNDS[1][0] <= row["share_logit_scale"] <= PARAMETER_BOUNDS[1][1]
        for row in folds
    )
    checks = {
        "ah_brier_vs_totals_only_upper_95_le_zero": paired["ah_brier_vs_totals_only"]["upper_95"]
        <= 0,
        "scoreline_nll_vs_totals_only_upper_95_le_zero": paired["scoreline_nll_vs_totals_only"][
            "upper_95"
        ]
        <= 0,
        "ah_brier_vs_production_current_upper_95_le_zero": paired["ah_brier_vs_production_current"][
            "upper_95"
        ]
        <= 0,
        "scoreline_nll_vs_production_current_upper_95_le_zero": paired[
            "scoreline_nll_vs_production_current"
        ]["upper_95"]
        <= 0,
        "minimum_7_folds_improve": folds_improved >= 7,
        "minimum_10_lines_improve": lines_improved >= 10,
        "margin_slope_closer_to_one": abs(candidate_margin["slope"] - 1)
        < abs(baseline_margin["slope"] - 1),
        "absolute_margin_intercept_le_0_10": abs(candidate_margin["intercept"]) <= 0.1,
        "total_lambda_max_difference_le_1e_12": total_lambda_max_difference <= 1e-12,
        "total_nll_max_difference_le_1e_12": total_nll_max_difference <= 1e-12,
        "lambda_clamp_count_zero": arms["candidate"]["metrics"]["lambda_clamp_count"] == 0,
        "fitted_parameters_inside_bounds": parameters_inside_bounds,
    }
    return {
        "fixture_count": len(oof_rows),
        "folds": folds,
        "metrics": {name: value["metrics"] for name, value in arms.items()},
        "line_ah_brier": {name: value["line_ah_brier"] for name, value in arms.items()},
        "paired_differences": paired,
        "folds_improved": folds_improved,
        "lines_improved": lines_improved,
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
    oof["checks"]["fitted_parameters_inside_bounds"] = (
        oof["checks"]["fitted_parameters_inside_bounds"] and full_inside_bounds
    )
    oof["passes"] = all(oof["checks"].values())
    return {
        "schema": "w2.v1.ah_goal_share_calibration_fit.v1",
        "sources": sources,
        "fixture_count": len(rows),
        "full_development_fit": {
            "share_intercept": full_parameters[0],
            "share_logit_scale": full_parameters[1],
        },
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
    lines = [
        "# V1 AH conditional goal-share 开发验收",
        "",
        f"决策：`{payload['decision']}`。",
        "",
        "严格 PIT / rolling-origin OOF 开发证据；不构成 calibration grant、部署授权、"
        "盈利证明或生产有效性证明。",
        "",
        f"- full fit: `{payload['full_development_fit']}`",
        f"- OOF fixtures: `{oof['fixture_count']}`",
        f"- improved folds/lines: `{oof['folds_improved']}/10`, `{oof['lines_improved']}/13`",
        f"- paired differences: `{oof['paired_differences']}`",
        "- margin regressions: `"
        f"{ {name: values['margin_regression'] for name, values in oof['metrics'].items()} }`",
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
        "121 注与 259 场市场 artifact 均未加载，不能选择参数、修改门槛或决定通过。",
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
