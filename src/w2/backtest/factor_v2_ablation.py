from __future__ import annotations

from math import exp
from typing import Any

from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.factor_model.pit_dataset import verify_normalized_feature_vector
from w2.models.dixon_coles import one_x_two_from_matrix
from w2.strategy.calibration import calibrate_lambdas
from w2.strategy.simulate import exact_score_matrix_from_lambdas

FACTOR_V2_ABLATION_SCHEMA_VERSION = "w2.factor_model.ablation.v1"


def build_b0_b1_b2_ablation(
    *,
    fixture_id: str,
    home_xg_for: float,
    home_xg_against: float,
    away_xg_for: float,
    away_xg_against: float,
    production_lambda_home: float,
    production_lambda_away: float,
    production_capture_identity_hash: str,
    normalized_features: dict[str, Any],
    factor_calibration: dict[str, Any],
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
    design = _design_vector(normalized_features)
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
        "B1_CURRENT_PRODUCTION": _track(
            lambda_home=production_lambda_home,
            lambda_away=production_lambda_away,
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
        "production_capture_identity_hash": str(production_capture_identity_hash),
        "normalized_features_sha256": str(normalized_features["normalized_features_sha256"]),
        "factor_calibration_sha256": str(factor_calibration["calibration_sha256"]),
        "design_vector": design,
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
    rho: float = 0.0,
    max_goals: int = 12,
) -> dict[str, Any]:
    body = {
        "schema_version": "w2.factor_model.ablation_calibration.v1",
        "calibration_version": str(calibration_version),
        "fit_split": "TRAIN",
        "split_manifest_sha256": str(split_manifest_sha256),
        "preprocessing_sha256": str(preprocessing_sha256),
        "relative_coefficients": dict(sorted(relative_coefficients.items())),
        "total_coefficients": dict(sorted(total_coefficients.items())),
        "admitted_for_historical_replay": bool(admitted_for_historical_replay),
        "admitted_for_forward_shadow": False,
        "rho": float(rho),
        "max_goals": int(max_goals),
    }
    return {**body, "calibration_sha256": _hash("FACTOR_MODEL_ABLATION_CALIBRATION", body)}


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


def _design_vector(normalized_features: dict[str, Any]) -> dict[str, float]:
    vector: dict[str, float] = {}
    for factor_id, factor in sorted(normalized_features["factors"].items()):
        if factor.get("status") != "READY" or factor.get("normalized_value") is None:
            raise ValueError("FACTOR_ABLATION_NORMALIZED_INPUT_NOT_READY")
        vector[f"{factor_id}.value"] = float(factor["normalized_value"])
        vector[f"{factor_id}.missing"] = float(factor["missing_indicator"])
    return vector


def _linear_predictor(design: dict[str, float], coefficients: dict[str, Any]) -> float:
    unknown = set(coefficients) - set(design)
    if unknown:
        raise ValueError("FACTOR_ABLATION_COEFFICIENT_INPUT_UNKNOWN")
    return sum(float(coefficients.get(name, 0.0)) * value for name, value in design.items())


def _verify_factor_calibration(artifact: dict[str, Any]) -> None:
    if artifact.get("schema_version") != "w2.factor_model.ablation_calibration.v1":
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


def _hash(identity_type: str, body: dict[str, Any]) -> str:
    return canonical_sha256(
        {"identity_type": identity_type, **body},
        domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
    )
