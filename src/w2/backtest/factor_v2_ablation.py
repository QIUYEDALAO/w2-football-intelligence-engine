from __future__ import annotations

from math import exp, isfinite, log
from typing import Any

from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.factor_model.ablation_scoring import (
    FACTOR_V2_ABLATION_SCHEMA_VERSION,
    FACTOR_V2_CALIBRATION_SCHEMA_VERSION,
    build_b0_b1_b2_ablation,
    design_vector,
)

__all__ = (
    "FACTOR_V2_ABLATION_SCHEMA_VERSION",
    "FACTOR_V2_CALIBRATION_SCHEMA_VERSION",
    "build_b0_b1_b2_ablation",
    "factor_calibration_artifact",
    "fit_poisson_factor_coefficients",
)


def factor_calibration_artifact(
    *,
    calibration_version: str,
    split_manifest_sha256: str,
    preprocessing_sha256: str,
    relative_coefficients: dict[str, float],
    total_coefficients: dict[str, float],
    admitted_for_historical_replay: bool,
    active_factor_ids: tuple[str, ...] | None = None,
    excluded_factor_statuses: dict[str, str] | None = None,
    feature_bounds: dict[str, dict[str, float]] | None = None,
    fit_diagnostics: dict[str, Any] | None = None,
    rho: float = 0.0,
    max_goals: int = 12,
) -> dict[str, Any]:
    inferred_factor_ids = {
        name.partition(".")[0]
        for name in (*relative_coefficients, *total_coefficients)
        if "." in name
    }
    active = tuple(sorted(active_factor_ids or inferred_factor_ids))
    body = {
        "schema_version": FACTOR_V2_CALIBRATION_SCHEMA_VERSION,
        "calibration_version": str(calibration_version),
        "fit_split": "TRAIN",
        "split_manifest_sha256": str(split_manifest_sha256),
        "preprocessing_sha256": str(preprocessing_sha256),
        "relative_coefficients": dict(sorted(relative_coefficients.items())),
        "total_coefficients": dict(sorted(total_coefficients.items())),
        "active_factor_ids": list(active),
        "excluded_factor_statuses": dict(sorted((excluded_factor_statuses or {}).items())),
        "feature_bounds": dict(sorted((feature_bounds or {}).items())),
        "fit_diagnostics": dict(fit_diagnostics or {}),
        "admitted_for_historical_replay": bool(admitted_for_historical_replay),
        "admitted_for_forward_shadow": False,
        "rho": float(rho),
        "max_goals": int(max_goals),
    }
    return {**body, "calibration_sha256": _hash("FACTOR_MODEL_ABLATION_CALIBRATION", body)}


def fit_poisson_factor_coefficients(
    rows: list[dict[str, Any]],
    *,
    active_factor_ids: tuple[str, ...],
    max_iterations: int = 50,
    tolerance: float = 1e-9,
) -> dict[str, Any]:
    """Fit relative/total lambda adjustments on TRAIN rows only."""
    if not rows or not active_factor_ids:
        raise ValueError("FACTOR_CALIBRATION_TRAIN_INPUT_EMPTY")
    names = tuple(
        name
        for factor_id in active_factor_ids
        for name in (f"{factor_id}.value", f"{factor_id}.missing")
    )
    training: list[tuple[list[float], float, float, int, int]] = []
    for row in rows:
        design = design_vector(
            row["normalized_features"], active_factor_ids=active_factor_ids
        )
        baseline_home = float(row["baseline_lambda_home"])
        baseline_away = float(row["baseline_lambda_away"])
        if baseline_home <= 0 or baseline_away <= 0:
            raise ValueError("FACTOR_CALIBRATION_BASELINE_INVALID")
        training.append(
            (
                [design[name] for name in names],
                baseline_home,
                baseline_away,
                int(row["home_goals"]),
                int(row["away_goals"]),
            )
        )

    width = len(names)
    feature_bounds = {
        name: {
            "minimum": min(row[0][index] for row in training),
            "maximum": max(row[0][index] for row in training),
        }
        for index, name in enumerate(names)
    }
    coefficients = [0.0] * (width * 2)
    converged = False
    iterations = 0
    ridge = 1e-8

    def evaluate(values: list[float], *, derivatives: bool) -> tuple[Any, ...]:
        relative = values[:width]
        total = values[width:]
        loss = 0.0
        gradient = [0.0] * (width * 2)
        hessian = [[0.0] * (width * 2) for _ in range(width * 2)]
        for design, base_home, base_away, home_goals, away_goals in training:
            relative_eta = sum(
                value * weight for value, weight in zip(design, relative, strict=True)
            )
            total_eta = sum(
                value * weight for value, weight in zip(design, total, strict=True)
            )
            home_eta = (total_eta + relative_eta) / 2.0
            away_eta = (total_eta - relative_eta) / 2.0
            if max(abs(home_eta), abs(away_eta)) > 50:
                return float("inf"), gradient, hessian
            lambda_home = base_home * exp(home_eta)
            lambda_away = base_away * exp(away_eta)
            loss += (
                lambda_home
                - home_goals * (log(base_home) + home_eta)
                + lambda_away
                - away_goals * (log(base_away) + away_eta)
            )
            if not derivatives:
                continue
            residual_home = lambda_home - home_goals
            residual_away = lambda_away - away_goals
            for left, x_left in enumerate(design):
                gradient[left] += 0.5 * (residual_home - residual_away) * x_left
                gradient[width + left] += 0.5 * (residual_home + residual_away) * x_left
                for right, x_right in enumerate(design):
                    same = 0.25 * (lambda_home + lambda_away) * x_left * x_right
                    cross = 0.25 * (lambda_home - lambda_away) * x_left * x_right
                    hessian[left][right] += same
                    hessian[width + left][width + right] += same
                    hessian[left][width + right] += cross
                    hessian[width + left][right] += cross
        return loss, gradient, hessian

    initial_loss = float(evaluate(coefficients, derivatives=False)[0])
    loss = initial_loss
    for iteration in range(1, max_iterations + 1):
        iterations = iteration
        loss, gradient, hessian = evaluate(coefficients, derivatives=True)
        for index in range(len(hessian)):
            hessian[index][index] += ridge
        step = _solve_linear_system(hessian, gradient)
        scale = 1.0
        accepted = False
        while scale >= 2**-20:
            candidate = [
                value - scale * delta
                for value, delta in zip(coefficients, step, strict=True)
            ]
            candidate_loss = float(evaluate(candidate, derivatives=False)[0])
            if isfinite(candidate_loss) and candidate_loss <= loss:
                coefficients = candidate
                loss = candidate_loss
                accepted = True
                break
            scale /= 2.0
        if not accepted:
            break
        if max(abs(scale * value) for value in step) <= tolerance:
            converged = True
            break
    if not converged:
        raise ValueError("FACTOR_CALIBRATION_OPTIMIZER_NOT_CONVERGED")
    return {
        "relative_coefficients": dict(zip(names, coefficients[:width], strict=True)),
        "total_coefficients": dict(zip(names, coefficients[width:], strict=True)),
        "feature_bounds": feature_bounds,
        "diagnostics": {
            "optimizer": "NEWTON_RAPHSON_BACKTRACKING_V1",
            "fit_split": "TRAIN",
            "training_fixture_count": len(training),
            "iterations": iterations,
            "converged": converged,
            "initial_poisson_nll": round(initial_loss, 9),
            "final_poisson_nll": round(loss, 9),
            "numerical_ridge": ridge,
        },
    }


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    augmented = [row[:] + [value] for row, value in zip(matrix, vector, strict=True)]
    size = len(vector)
    for pivot in range(size):
        best = max(range(pivot, size), key=lambda row: abs(augmented[row][pivot]))
        if abs(augmented[best][pivot]) < 1e-12:
            raise ValueError("FACTOR_CALIBRATION_HESSIAN_SINGULAR")
        augmented[pivot], augmented[best] = augmented[best], augmented[pivot]
        divisor = augmented[pivot][pivot]
        augmented[pivot] = [value / divisor for value in augmented[pivot]]
        for row in range(size):
            if row == pivot:
                continue
            multiplier = augmented[row][pivot]
            augmented[row] = [
                value - multiplier * pivot_value
                for value, pivot_value in zip(
                    augmented[row], augmented[pivot], strict=True
                )
            ]
    return [augmented[row][-1] for row in range(size)]


def _hash(identity_type: str, body: dict[str, Any]) -> str:
    return canonical_sha256(
        {"identity_type": identity_type, **body},
        domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
    )
