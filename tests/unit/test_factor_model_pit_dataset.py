from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.factor_model.pit_dataset import (
    TemporalSplitPolicy,
    build_temporal_split_manifest,
    fit_train_only_preprocessing,
    normalize_pit_feature_snapshot,
)
from w2.factor_model.pit_features import PIT_FEATURE_SNAPSHOT_SCHEMA_VERSION

START = datetime(2023, 1, 1, tzinfo=UTC)
POLICY = TemporalSplitPolicy(
    version="split-v1.test",
    train_start=START,
    train_end=START + timedelta(days=100),
    validation_end=START + timedelta(days=200),
    holdout_end=START + timedelta(days=300),
)


def _snapshot(fixture_id: str, kickoff: datetime, f3: float | None) -> dict[str, Any]:
    body = {
        "schema_version": PIT_FEATURE_SNAPSHOT_SCHEMA_VERSION,
        "target_fixture_id": fixture_id,
        "target_kickoff": kickoff,
        "feature_as_of": kickoff,
        "home_team_id": "home",
        "away_team_id": "away",
        "pit_history_manifest_sha256": "a" * 64,
        "rating_policy": {},
        "factors": {
            factor_id: {
                "missing": value is None,
                "raw_value": value,
            }
            for factor_id, value in {
                "F3_REST_FITNESS": f3,
                "F6_H2H": 0.5,
                "F7_STRENGTH_FORM": 25.0,
            }.items()
        },
        "numeric_effect_enabled": False,
        "candidate_eligible": False,
        "notification_eligible": False,
    }
    return {
        **body,
        "feature_snapshot_sha256": canonical_sha256(
            {"identity_type": "FACTOR_MODEL_PIT_FEATURE_SNAPSHOT", **body},
            domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
        ),
    }


def test_temporal_split_boundaries_are_half_open_and_deterministic() -> None:
    snapshots = [
        _snapshot("train", POLICY.train_start, 1.0),
        _snapshot("validation", POLICY.train_end, 2.0),
        _snapshot("holdout", POLICY.validation_end, 3.0),
        _snapshot("excluded", POLICY.holdout_end, 4.0),
    ]

    manifest = build_temporal_split_manifest(snapshots, policy=POLICY)

    assert [(row["fixture_id"], row["split"]) for row in manifest["targets"]] == [
        ("train", "TRAIN"),
        ("validation", "VALIDATION"),
        ("holdout", "HOLDOUT"),
    ]
    assert manifest["counts"] == {"TRAIN": 1, "VALIDATION": 1, "HOLDOUT": 1}
    assert manifest["excluded_out_of_range"] == 1


def test_preprocessing_fits_train_only_and_ignores_validation_extreme() -> None:
    train_one = _snapshot("train-1", START + timedelta(days=1), 1.0)
    train_two = _snapshot("train-2", START + timedelta(days=2), 3.0)
    validation = _snapshot("validation", POLICY.train_end, 1000.0)
    snapshots = [train_one, train_two, validation]
    split = build_temporal_split_manifest(snapshots, policy=POLICY)

    artifact = fit_train_only_preprocessing(split, snapshots)

    f3 = artifact["parameters"]["F3_REST_FITNESS"]
    assert artifact["fit_split"] == "TRAIN"
    assert f3["mean"] == 2.0
    assert f3["standard_deviation"] == 1.0
    assert f3["training_fixture_ids"] == ["train-1", "train-2"]


def test_missing_value_uses_train_mean_and_separate_indicator() -> None:
    observed = _snapshot("train-1", START + timedelta(days=1), 2.0)
    missing = _snapshot("validation", POLICY.train_end, None)
    snapshots = [observed, missing]
    split = build_temporal_split_manifest(snapshots, policy=POLICY)
    artifact = fit_train_only_preprocessing(split, snapshots)

    normalized = normalize_pit_feature_snapshot(missing, artifact)

    f3 = normalized["factors"]["F3_REST_FITNESS"]
    assert f3["raw_value"] is None
    assert f3["normalized_value"] == 0.0
    assert f3["missing_indicator"] == 1
    assert f3["imputation_applied"] is True
    assert normalized["numeric_effect_enabled"] is False


def test_tampered_snapshot_and_split_artifact_fail_closed() -> None:
    snapshot = _snapshot("train", START + timedelta(days=1), 1.0)
    tampered = deepcopy(snapshot)
    tampered["factors"]["F3_REST_FITNESS"]["raw_value"] = 99.0
    with pytest.raises(ValueError, match="SNAPSHOT_HASH_MISMATCH"):
        build_temporal_split_manifest([tampered], policy=POLICY)

    split = build_temporal_split_manifest([snapshot], policy=POLICY)
    split["counts"]["TRAIN"] = 99
    with pytest.raises(ValueError, match="SPLIT_MANIFEST_HASH_MISMATCH"):
        fit_train_only_preprocessing(split, [snapshot])


def test_duplicate_fixture_with_different_snapshot_fails_closed() -> None:
    first = _snapshot("same", START - timedelta(days=2), 1.0)
    second = _snapshot("same", START - timedelta(days=1), 1.0)

    with pytest.raises(ValueError, match="TEMPORAL_SPLIT_FIXTURE_CONFLICT"):
        build_temporal_split_manifest([first, second], policy=POLICY)
