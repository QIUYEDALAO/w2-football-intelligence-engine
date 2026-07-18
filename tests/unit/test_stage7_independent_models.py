from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from w2.models.calibration import CalibrationMethod, apply_calibration, fit_calibration
from w2.models.evaluation import paired_bootstrap_delta
from w2.models.independent import (
    AsOfFeatureBuilder,
    MatchRecord,
    ModelFamily,
    artifact_hash,
    assert_feature_allowlist,
    predict_from_features,
)
from w2.models.residuals import independent_minus_market, residual_blend_research_only

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def match(index: int, neutral: bool = False) -> MatchRecord:
    return MatchRecord(
        fixture_id=f"fixture-{index}",
        competition="World Cup 2022",
        season="2022",
        kickoff_utc=NOW + timedelta(days=index),
        home_team="alpha",
        away_team="beta",
        home_goals=2 if index % 2 else 0,
        away_goals=1,
        neutral_site=neutral,
    )


def test_feature_allowlist_rejects_market_fields_and_uses_asof_state() -> None:
    builder = AsOfFeatureBuilder()
    first = match(1, neutral=True)
    features = builder.features(first)
    assert features["neutral_site"] is True
    assert features["home_field"] == 0.0
    with pytest.raises(ValueError):
        assert_feature_allowlist({"odds_1x2_home": 2.0})
    builder.update(first)
    second_features = builder.features(match(10))
    assert second_features["home_sample_size"] == 1.0
    assert second_features["away_sample_size"] == 1.0


def test_all_model_families_emit_normalized_probabilities_and_score_matrix() -> None:
    builder = AsOfFeatureBuilder()
    features = builder.features(match(1))
    for family in ModelFamily:
        if family == ModelFamily.VALIDATION_ENSEMBLE:
            continue
        prediction = predict_from_features("fixture", family, features, NOW)
        assert abs(sum(prediction.one_x_two.values()) - 1.0) < 1e-9
        assert abs(sum(prediction.score_matrix.values()) - 1.0) < 1e-9
        assert set(prediction.totals) == {"OVER_2_5", "UNDER_2_5"}
        assert set(prediction.btts) == {"YES", "NO"}


def test_sparse_team_shrinkage_and_parameter_isolation() -> None:
    national_builder = AsOfFeatureBuilder()
    club_builder = AsOfFeatureBuilder()
    national_builder.update(match(1))
    assert national_builder.features(match(2))["home_sample_size"] == 1.0
    assert club_builder.features(match(2))["home_sample_size"] == 0.0


def test_rolling_form_persists_empty_existing_and_multiple_updates() -> None:
    builder = AsOfFeatureBuilder()
    assert builder.features(match(1))["rolling_home_form"] == 0.0

    builder.update(match(1))
    assert builder.states["alpha"].form_points == [3.0]
    assert builder.states["beta"].form_points == [0.0]
    assert builder.features(match(2))["rolling_home_form"] == 1.0

    builder.update(match(2))
    builder.update(match(3))
    assert builder.states["alpha"].form_points == [3.0, 0.0, 3.0]
    assert builder.states["beta"].form_points == [0.0, 3.0, 0.0]
    assert builder.features(match(4))["rolling_home_form"] == pytest.approx(2 / 3)


def test_rolling_form_snapshot_roundtrip_and_replay_are_deterministic() -> None:
    uninterrupted = AsOfFeatureBuilder()
    restored_source = AsOfFeatureBuilder()
    for record in (match(1), match(2)):
        uninterrupted.update(record)
        restored_source.update(record)

    serialized = json.dumps(restored_source.snapshot(), sort_keys=True)
    restored = AsOfFeatureBuilder.from_snapshot(json.loads(serialized))
    assert restored.snapshot() == restored_source.snapshot()

    for record in (match(3), match(4), match(5), match(6)):
        uninterrupted.update(record)
        restored.update(record)

    assert restored.snapshot() == uninterrupted.snapshot()
    assert restored.features(match(10)) == uninterrupted.features(match(10))


def test_rolling_form_snapshot_fails_closed_on_unknown_schema() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        AsOfFeatureBuilder.from_snapshot({"schema_version": "legacy", "teams": {}})


def test_calibration_validation_artifact_and_residual_research_isolation() -> None:
    rows = [
        ({"HOME": 0.5, "DRAW": 0.25, "AWAY": 0.25}, "HOME"),
        ({"HOME": 0.4, "DRAW": 0.3, "AWAY": 0.3}, "AWAY"),
    ]
    artifact = fit_calibration(rows, CalibrationMethod.PLATT, fitted_on="validation")
    assert artifact.fitted_on == "validation"
    calibrated = apply_calibration(rows[0][0], artifact)
    assert abs(sum(calibrated.values()) - 1.0) < 1e-9
    residual = independent_minus_market(
        {"HOME": 0.4, "DRAW": 0.3, "AWAY": 0.3},
        {"HOME": 0.5, "DRAW": 0.25, "AWAY": 0.25},
    )
    assert residual["HOME"] == pytest.approx(-0.1)
    blend = residual_blend_research_only(
        {"HOME": 0.4, "DRAW": 0.3, "AWAY": 0.3},
        {"HOME": 0.5, "DRAW": 0.25, "AWAY": 0.25},
        0.2,
    )
    assert abs(sum(blend.values()) - 1.0) < 1e-9


def test_paired_bootstrap_and_deterministic_artifact_hash() -> None:
    interval = paired_bootstrap_delta([0.9, 1.0, 1.1], [1.0, 1.1, 1.2], samples=40)
    assert interval["ci_high"] < 0
    assert artifact_hash({"b": 2, "a": 1}) == artifact_hash({"a": 1, "b": 2})
