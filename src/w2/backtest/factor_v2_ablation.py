from __future__ import annotations

from math import exp, isfinite, log
from typing import Any

from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.factor_model.pit_dataset import verify_normalized_feature_vector
from w2.models.dixon_coles import one_x_two_from_matrix
from w2.strategy.calibration import calibrate_lambdas
from w2.strategy.simulate import exact_score_matrix_from_lambdas

FACTOR_V2_ABLATION_SCHEMA_VERSION = "w2.factor_model.ablation.v2"
FACTOR_V2_CALIBRATION_SCHEMA_VERSION = "w2.factor_model.ablation_calibration.v2"
B1_TRACK_IDS = {"B1_CURRENT_PRODUCTION", "B1_RECOMPUTED"}


def build_b0_b1_b2_ablation(
    *,
    fixture_id: str,
    home_xg_for: float,
    home_xg_against: float,
    away_xg_for: float,
    away_xg_against: float,
    b1_lambda_home: float,
    b1_lambda_away: float,
    b1_input_identity_hash: str,
    normalized_features: dict[str, Any],
    factor_calibration: dict[str, Any],
    b1_track_id: str = "B1_CURRENT_PRODUCTION",
) -> dict[str, Any]:
    """Build offline B0/B1/B2 outputs through one exact score-matrix engine."""
    verify_normalized_feature_vector(normalized_features)
    _verify_factor_calibration(factor_calibration)
    if factor_calibration["preprocessing_sha256"] != normalized_features[
        "preprocessing_sha256"
    ]:
        raise ValueError("FACTOR_ABLATION_PREPROCESSING_MISMATCH")
    baseline = calibrate_lambdas(
        home_xg_for=home_xg_for,
        home_xg_against=home_xg_against,
        away_xg_for=away_xg_for,
        away_xg_against=away_xg_against,
        home_elo=None,
        away_elo=None,
        home_squad_value_eur=None,
        away_squad_value_eur=None,
    )
    if b1_track_id not in B1_TRACK_IDS:
        raise ValueError("FACTOR_ABLATION_B1_TRACK_INVALID")
    unbounded_design = _design_vector(
        normalized_features,
        active_factor_ids=tuple(factor_calibration["active_factor_ids"]),
    )
    design = _apply_feature_bounds(
        unbounded_design,
        bounds=factor_calibration.get("feature_bounds", {}),
    )
    relative = _linear_predictor(design, factor_calibration["relative_coefficients"])
    total = _linear_predictor(design, factor_calibration["total_coefficients"])
    b2_home = baseline.lambda_home * exp((total + relative) / 2.0)
    b2_away = baseline.lambda_away * exp((total - relative) / 2.0)
    max_goals = int(factor_calibration["max_goals"])
    rho = float(factor_calibration["rho"])

    tracks = {
        "B0_SAME_ENGINE_XG": _track(
            lambda_home=baseline.lambda_home,
            lambda_away=baseline.lambda_away,
            rho=rho,
            max_goals=max_goals,
        ),
        b1_track_id: _track(
            lambda_home=b1_lambda_home,
            lambda_away=b1_lambda_away,
            rho=rho,
            max_goals=max_goals,
        ),
        "B2_FACTOR_V2": _track(
            lambda_home=b2_home,
            lambda_away=b2_away,
            rho=rho,
            max_goals=max_goals,
        ),
    }
    body = {
        "schema_version": FACTOR_V2_ABLATION_SCHEMA_VERSION,
        "fixture_id": str(fixture_id),
        "b1_input_identity_hash": str(b1_input_identity_hash),
        "b1_track_id": b1_track_id,
        "normalized_features_sha256": str(normalized_features["normalized_features_sha256"]),
        "factor_calibration_sha256": str(factor_calibration["calibration_sha256"]),
        "design_vector": design,
        "feature_bound_clip_count": sum(
            design[name] != value for name, value in unbounded_design.items()
        ),
        "tracks": tracks,
        "candidate_eligible": False,
        "notification_eligible": False,
        "outcome_ledger_eligible": False,
    }
    return {
        **body,
        "ablation_sha256": _hash("FACTOR_MODEL_B0_B1_B2_ABLATION", body),
    }


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
        design = _design_vector(
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


def _track(
    *,
    lambda_home: float,
    lambda_away: float,
    rho: float,
    max_goals: int,
) -> dict[str, Any]:
    matrix = exact_score_matrix_from_lambdas(
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        rho=rho,
        max_goals=max_goals,
    )
    rows = [
        {
            "home_goals": home,
            "away_goals": away,
            "probability": round(probability, 12),
        }
        for (home, away), probability in sorted(matrix.items())
    ]
    return {
        "lambda_home": round(float(lambda_home), 6),
        "lambda_away": round(float(lambda_away), 6),
        "probability_method": "EXACT_MATRIX",
        "sampling_used": False,
        "rho": rho,
        "max_goals": max_goals,
        "score_matrix_probability_sum": sum(matrix.values()),
        "score_matrix_sha256": _hash("FACTOR_MODEL_SCORE_MATRIX", {"rows": rows}),
        "one_x_two": one_x_two_from_matrix(matrix),
    }


def _design_vector(
    normalized_features: dict[str, Any], *, active_factor_ids: tuple[str, ...]
) -> dict[str, float]:
    vector: dict[str, float] = {}
    for factor_id in sorted(active_factor_ids):
        factor = normalized_features["factors"].get(factor_id)
        if factor is None:
            raise ValueError("FACTOR_ABLATION_NORMALIZED_INPUT_NOT_READY")
        if factor.get("status") != "READY" or factor.get("normalized_value") is None:
            raise ValueError("FACTOR_ABLATION_NORMALIZED_INPUT_NOT_READY")
        vector[f"{factor_id}.value"] = float(factor["normalized_value"])
        vector[f"{factor_id}.missing"] = float(factor["missing_indicator"])
    return vector


def _apply_feature_bounds(
    design: dict[str, float], *, bounds: dict[str, Any]
) -> dict[str, float]:
    if not bounds:
        return design
    if set(bounds) != set(design):
        raise ValueError("FACTOR_ABLATION_FEATURE_BOUNDS_MISMATCH")
    return {
        name: min(
            max(value, float(bounds[name]["minimum"])),
            float(bounds[name]["maximum"]),
        )
        for name, value in design.items()
    }


def _linear_predictor(design: dict[str, float], coefficients: dict[str, Any]) -> float:
    unknown = set(coefficients) - set(design)
    if unknown:
        raise ValueError("FACTOR_ABLATION_COEFFICIENT_INPUT_UNKNOWN")
    return sum(float(coefficients.get(name, 0.0)) * value for name, value in design.items())


def _verify_factor_calibration(artifact: dict[str, Any]) -> None:
    if artifact.get("schema_version") != FACTOR_V2_CALIBRATION_SCHEMA_VERSION:
        raise ValueError("FACTOR_ABLATION_CALIBRATION_SCHEMA_INVALID")
    body = {key: value for key, value in artifact.items() if key != "calibration_sha256"}
    if artifact.get("calibration_sha256") != _hash("FACTOR_MODEL_ABLATION_CALIBRATION", body):
        raise ValueError("FACTOR_ABLATION_CALIBRATION_HASH_MISMATCH")
    if artifact.get("fit_split") != "TRAIN" or not artifact.get(
        "admitted_for_historical_replay"
    ):
        raise ValueError("FACTOR_ABLATION_CALIBRATION_NOT_ADMITTED")
    if float(artifact.get("rho", 1.0)) != 0.0 or int(artifact.get("max_goals", 0)) != 12:
        raise ValueError("FACTOR_ABLATION_ENGINE_CONTRACT_MISMATCH")


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
