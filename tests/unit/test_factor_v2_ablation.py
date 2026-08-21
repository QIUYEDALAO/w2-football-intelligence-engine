from __future__ import annotations

from copy import deepcopy

import pytest

from w2.backtest.factor_v2_ablation import (
    build_b0_b1_b2_ablation,
    factor_calibration_artifact,
)
from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.factor_model.pit_dataset import NORMALIZED_FEATURE_SCHEMA_VERSION


def _normalized() -> dict[str, object]:
    body = {
        "schema_version": NORMALIZED_FEATURE_SCHEMA_VERSION,
        "target_fixture_id": "api_football:target",
        "feature_snapshot_sha256": "a" * 64,
        "preprocessing_sha256": "b" * 64,
        "factors": {
            "F3_REST_FITNESS": {
                "status": "READY",
                "raw_value": 2.0,
                "normalized_value": 1.0,
                "missing_indicator": 0,
                "imputation_applied": False,
            },
            "F6_H2H": {
                "status": "READY",
                "raw_value": None,
                "normalized_value": 0.0,
                "missing_indicator": 1,
                "imputation_applied": True,
            },
            "F7_STRENGTH_FORM": {
                "status": "READY",
                "raw_value": 40.0,
                "normalized_value": 0.5,
                "missing_indicator": 0,
                "imputation_applied": False,
            },
        },
        "numeric_effect_enabled": False,
    }
    return {
        **body,
        "normalized_features_sha256": canonical_sha256(
            {"identity_type": "NORMALIZED_FEATURES", **body},
            domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
        ),
    }


def _calibration(*, f7: float = 0.0, admitted: bool = True) -> dict[str, object]:
    return factor_calibration_artifact(
        calibration_version="factor-v2.test",
        split_manifest_sha256="c" * 64,
        preprocessing_sha256="b" * 64,
        relative_coefficients={"F7_STRENGTH_FORM.value": f7},
        total_coefficients={},
        admitted_for_historical_replay=admitted,
    )


def _ablation(calibration: dict[str, object]) -> dict[str, object]:
    return build_b0_b1_b2_ablation(
        fixture_id="api_football:target",
        home_xg_for=1.5,
        home_xg_against=1.1,
        away_xg_for=1.2,
        away_xg_against=1.4,
        production_lambda_home=1.72,
        production_lambda_away=1.08,
        production_capture_identity_hash="d" * 64,
        normalized_features=_normalized(),
        factor_calibration=calibration,
    )


def test_b0_b1_b2_use_one_exact_13x13_engine_without_sampling() -> None:
    result = _ablation(_calibration())
    tracks = result["tracks"]

    assert set(tracks) == {
        "B0_SAME_ENGINE_XG",
        "B1_CURRENT_PRODUCTION",
        "B2_FACTOR_V2",
    }
    assert all(track["probability_method"] == "EXACT_MATRIX" for track in tracks.values())
    assert all(track["sampling_used"] is False for track in tracks.values())
    assert all(track["max_goals"] == 12 for track in tracks.values())
    assert all(track["rho"] == 0.0 for track in tracks.values())
    assert all(
        track["score_matrix_probability_sum"] == pytest.approx(1.0)
        for track in tracks.values()
    )
    assert tracks["B0_SAME_ENGINE_XG"]["score_matrix_sha256"] == tracks["B2_FACTOR_V2"][
        "score_matrix_sha256"
    ]
    assert result["candidate_eligible"] is False
    assert result["notification_eligible"] is False
    assert result["outcome_ledger_eligible"] is False


def test_relative_factor_moves_home_and_away_lambdas_in_opposite_directions() -> None:
    neutral = _ablation(_calibration(f7=0.0))["tracks"]["B2_FACTOR_V2"]
    adjusted = _ablation(_calibration(f7=0.4))["tracks"]["B2_FACTOR_V2"]

    assert adjusted["lambda_home"] > neutral["lambda_home"]
    assert adjusted["lambda_away"] < neutral["lambda_away"]


def test_unadmitted_or_tampered_calibration_fails_closed() -> None:
    with pytest.raises(ValueError, match="CALIBRATION_NOT_ADMITTED"):
        _ablation(_calibration(admitted=False))

    tampered = deepcopy(_calibration())
    tampered["rho"] = 0.1
    with pytest.raises(ValueError, match="CALIBRATION_HASH_MISMATCH"):
        _ablation(tampered)


def test_calibration_and_normalized_features_must_share_preprocessing() -> None:
    mismatched = factor_calibration_artifact(
        calibration_version="factor-v2.test",
        split_manifest_sha256="c" * 64,
        preprocessing_sha256="e" * 64,
        relative_coefficients={},
        total_coefficients={},
        admitted_for_historical_replay=True,
    )

    with pytest.raises(ValueError, match="PREPROCESSING_MISMATCH"):
        _ablation(mismatched)
