from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
import scripts.publish_w2_r4_1_artifacts as publisher
import scripts.run_w2_market_baseline_eval as market_eval

from w2.models.r4_1_features import (
    r4_1_feature_rows,
    r4_1_offline_model_samples,
    r4_1_strength_features,
)


def test_eval_script_uses_shared_r4_1_feature_builder() -> None:
    assert market_eval.r4_1_offline_model_samples is r4_1_offline_model_samples


def test_r4_1_strength_features_are_deterministic_for_eval_and_serving_rows() -> None:
    histories = {
        ("league", "home"): [(1.4, 0.9), (1.2, 1.0)],
        ("league", "away"): [(0.8, 1.3), (1.1, 1.2)],
    }
    features = r4_1_strength_features(
        competition_id="league",
        histories=histories,
        home_key=("league", "home"),
        away_key=("league", "away"),
    )
    fixture = SimpleNamespace(competition_id="league")
    sample = SimpleNamespace(
        fixture=fixture,
        true_features={
            "elo_diff": 60.0,
            "home_field": 1.0,
            **features,
        },
    )

    home_row, away_row = r4_1_feature_rows(sample, ("league",))

    assert home_row == [
        1.0,
        1.0,
        features["home_attack_strength"],
        features["away_defence_strength"],
        0.15,
        1.0,
    ]
    assert away_row == [
        1.0,
        0.0,
        features["away_attack_strength"],
        features["home_defence_strength"],
        -0.15,
        0.0,
    ]


def test_publisher_target_set_excludes_brasileirao_guard() -> None:
    assert "brasileirao_serie_a" not in publisher.TARGET_COMPETITIONS


def test_protocol_identity_check_requires_eval_coefficients(monkeypatch: Any) -> None:
    model = SimpleNamespace(
        coefficients=(0.1, 0.2, 0.3),
        feature_names=("intercept", "home_field", "dixon_coles_rho=-0.03"),
    )
    monkeypatch.setattr(
        publisher,
        "_fit_protocol",
        lambda _samples: {
            "model": model,
            "temperature": 0.96,
            "fit_sample_count": 10,
            "train_cutoff_utc": datetime(2026, 1, 1, tzinfo=UTC),
        },
    )

    result = publisher._protocol_identity_check(
        name="protocol",
        samples=[object()],
        expected={
            "coefficients": [0.1, 0.2, 0.3],
            "temperature": 0.96,
            "policy": {"dixon_coles_rho": -0.03},
        },
    )

    assert result["status"] == "PASS"


def test_protocol_identity_check_fails_on_coefficients_mismatch(monkeypatch: Any) -> None:
    model = SimpleNamespace(
        coefficients=(0.1, 0.2, 0.4),
        feature_names=("intercept", "home_field", "dixon_coles_rho=-0.03"),
    )
    monkeypatch.setattr(
        publisher,
        "_fit_protocol",
        lambda _samples: {
            "model": model,
            "temperature": 0.96,
            "fit_sample_count": 10,
            "train_cutoff_utc": datetime(2026, 1, 1, tzinfo=UTC),
        },
    )

    with pytest.raises(SystemExit, match="protocol identity mismatch"):
        publisher._protocol_identity_check(
            name="protocol",
            samples=[object()],
            expected={
                "coefficients": [0.1, 0.2, 0.3],
                "temperature": 0.96,
                "policy": {"dixon_coles_rho": -0.03},
            },
        )
