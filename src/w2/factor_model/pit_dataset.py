from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import fmean, pstdev
from typing import Any

from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.factor_model.pit_features import verify_pit_feature_snapshot

TEMPORAL_SPLIT_MANIFEST_SCHEMA_VERSION = "w2.factor_model.temporal_split_manifest.v1"
TRAIN_PREPROCESSING_SCHEMA_VERSION = "w2.factor_model.train_preprocessing.v1"
NORMALIZED_FEATURE_SCHEMA_VERSION = "w2.factor_model.normalized_features.v1"


@dataclass(frozen=True, kw_only=True)
class TemporalSplitPolicy:
    version: str
    train_start: datetime
    train_end: datetime
    validation_end: datetime
    holdout_end: datetime

    def __post_init__(self) -> None:
        boundaries = tuple(
            _utc(value)
            for value in (
                self.train_start,
                self.train_end,
                self.validation_end,
                self.holdout_end,
            )
        )
        if not self.version or boundaries != tuple(sorted(set(boundaries))):
            raise ValueError("TEMPORAL_SPLIT_POLICY_INVALID")


def build_temporal_split_manifest(
    snapshots: list[dict[str, Any]],
    *,
    policy: TemporalSplitPolicy,
) -> dict[str, Any]:
    targets: dict[str, dict[str, Any]] = {}
    seen: dict[str, dict[str, Any]] = {}
    excluded = 0
    for snapshot in snapshots:
        verify_pit_feature_snapshot(snapshot)
        fixture_id = str(snapshot["target_fixture_id"])
        target: dict[str, Any] = {
            "fixture_id": fixture_id,
            "kickoff": _utc(snapshot["target_kickoff"]),
            "feature_snapshot_sha256": str(snapshot["feature_snapshot_sha256"]),
        }
        previous = seen.get(fixture_id)
        if previous is not None and previous != target:
            raise ValueError("TEMPORAL_SPLIT_FIXTURE_CONFLICT")
        if previous is not None:
            continue
        seen[fixture_id] = target
        split = _split(target["kickoff"], policy)
        if split is None:
            excluded += 1
            continue
        targets[fixture_id] = {**target, "split": split}

    rows = sorted(targets.values(), key=lambda row: (row["kickoff"], row["fixture_id"]))
    body = {
        "schema_version": TEMPORAL_SPLIT_MANIFEST_SCHEMA_VERSION,
        "policy_version": policy.version,
        "boundaries": {
            "train_start": _utc(policy.train_start),
            "train_end": _utc(policy.train_end),
            "validation_end": _utc(policy.validation_end),
            "holdout_end": _utc(policy.holdout_end),
        },
        "targets": rows,
        "counts": {
            split: sum(row["split"] == split for row in rows)
            for split in ("TRAIN", "VALIDATION", "HOLDOUT")
        },
        "excluded_out_of_range": excluded,
    }
    return {**body, "split_manifest_sha256": _hash("TEMPORAL_SPLIT_MANIFEST", body)}


def fit_train_only_preprocessing(
    split_manifest: dict[str, Any],
    snapshots: list[dict[str, Any]],
    *,
    factor_ids: tuple[str, ...] = ("F3_REST_FITNESS", "F6_H2H", "F7_STRENGTH_FORM"),
) -> dict[str, Any]:
    _verify_split_manifest(split_manifest)
    by_fixture: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        verified = verify_pit_feature_snapshot(snapshot)
        fixture_id = str(verified["target_fixture_id"])
        previous = by_fixture.get(fixture_id)
        if previous is not None and previous["feature_snapshot_sha256"] != verified[
            "feature_snapshot_sha256"
        ]:
            raise ValueError("TRAIN_PREPROCESSING_FIXTURE_CONFLICT")
        by_fixture[fixture_id] = verified
    train_ids = [
        row["fixture_id"] for row in split_manifest["targets"] if row["split"] == "TRAIN"
    ]
    if not train_ids:
        raise ValueError("TRAIN_PREPROCESSING_EMPTY_TRAIN_SPLIT")

    parameters: dict[str, dict[str, Any]] = {}
    for factor_id in factor_ids:
        observed: list[tuple[str, float]] = []
        missing_count = 0
        for fixture_id in train_ids:
            try:
                factor = by_fixture[fixture_id]["factors"][factor_id]
            except KeyError as exc:
                raise ValueError("TRAIN_PREPROCESSING_INPUT_MISSING") from exc
            raw = factor.get("raw_value")
            if factor.get("missing") is True or raw is None:
                missing_count += 1
            else:
                observed.append((fixture_id, float(raw)))
        values = [value for _, value in observed]
        parameters[factor_id] = {
            "status": "FITTED" if values else "UNFITTED_NO_TRAIN_VALUES",
            "mean": fmean(values) if values else None,
            "standard_deviation": pstdev(values) if len(values) > 1 else 0.0 if values else None,
            "observed_count": len(values),
            "missing_count": missing_count,
            "training_fixture_ids": [fixture_id for fixture_id, _ in observed],
        }

    body = {
        "schema_version": TRAIN_PREPROCESSING_SCHEMA_VERSION,
        "split_manifest_sha256": str(split_manifest["split_manifest_sha256"]),
        "fit_split": "TRAIN",
        "factor_ids": list(factor_ids),
        "missing_strategy": "TRAIN_MEAN_PLUS_MISSING_INDICATOR",
        "parameters": parameters,
    }
    return {**body, "preprocessing_sha256": _hash("TRAIN_PREPROCESSING", body)}


def normalize_pit_feature_snapshot(
    snapshot: dict[str, Any],
    preprocessing: dict[str, Any],
) -> dict[str, Any]:
    verify_pit_feature_snapshot(snapshot)
    _verify_preprocessing(preprocessing)
    normalized: dict[str, dict[str, Any]] = {}
    for factor_id in preprocessing["factor_ids"]:
        factor = snapshot["factors"][factor_id]
        parameter = preprocessing["parameters"][factor_id]
        if parameter["status"] != "FITTED":
            normalized[factor_id] = {
                "status": "UNAVAILABLE",
                "raw_value": factor.get("raw_value"),
                "normalized_value": None,
                "missing_indicator": int(bool(factor.get("missing"))),
                "imputation_applied": False,
            }
            continue
        missing = factor.get("missing") is True or factor.get("raw_value") is None
        raw = float(parameter["mean"] if missing else factor["raw_value"])
        standard_deviation = float(parameter["standard_deviation"])
        normalized[factor_id] = {
            "status": "READY",
            "raw_value": factor.get("raw_value"),
            "normalized_value": (raw - float(parameter["mean"]))
            / (standard_deviation or 1.0),
            "missing_indicator": int(missing),
            "imputation_applied": missing,
        }

    body = {
        "schema_version": NORMALIZED_FEATURE_SCHEMA_VERSION,
        "target_fixture_id": str(snapshot["target_fixture_id"]),
        "feature_snapshot_sha256": str(snapshot["feature_snapshot_sha256"]),
        "preprocessing_sha256": str(preprocessing["preprocessing_sha256"]),
        "factors": normalized,
        "numeric_effect_enabled": False,
    }
    return {**body, "normalized_features_sha256": _hash("NORMALIZED_FEATURES", body)}


def verify_normalized_feature_vector(vector: dict[str, Any]) -> dict[str, Any]:
    if vector.get("schema_version") != NORMALIZED_FEATURE_SCHEMA_VERSION:
        raise ValueError("NORMALIZED_FEATURES_SCHEMA_INVALID")
    body = {key: value for key, value in vector.items() if key != "normalized_features_sha256"}
    if vector.get("normalized_features_sha256") != _hash("NORMALIZED_FEATURES", body):
        raise ValueError("NORMALIZED_FEATURES_HASH_MISMATCH")
    return vector


def _split(kickoff: datetime, policy: TemporalSplitPolicy) -> str | None:
    if _utc(policy.train_start) <= kickoff < _utc(policy.train_end):
        return "TRAIN"
    if _utc(policy.train_end) <= kickoff < _utc(policy.validation_end):
        return "VALIDATION"
    if _utc(policy.validation_end) <= kickoff < _utc(policy.holdout_end):
        return "HOLDOUT"
    return None


def _verify_split_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != TEMPORAL_SPLIT_MANIFEST_SCHEMA_VERSION:
        raise ValueError("TEMPORAL_SPLIT_MANIFEST_SCHEMA_INVALID")
    body = {key: value for key, value in manifest.items() if key != "split_manifest_sha256"}
    if manifest.get("split_manifest_sha256") != _hash("TEMPORAL_SPLIT_MANIFEST", body):
        raise ValueError("TEMPORAL_SPLIT_MANIFEST_HASH_MISMATCH")


def _verify_preprocessing(artifact: dict[str, Any]) -> None:
    if artifact.get("schema_version") != TRAIN_PREPROCESSING_SCHEMA_VERSION:
        raise ValueError("TRAIN_PREPROCESSING_SCHEMA_INVALID")
    body = {key: value for key, value in artifact.items() if key != "preprocessing_sha256"}
    if artifact.get("preprocessing_sha256") != _hash("TRAIN_PREPROCESSING", body):
        raise ValueError("TRAIN_PREPROCESSING_HASH_MISMATCH")
    if artifact.get("fit_split") != "TRAIN":
        raise ValueError("TRAIN_PREPROCESSING_SPLIT_INVALID")


def _hash(identity_type: str, body: dict[str, Any]) -> str:
    return canonical_sha256(
        {"identity_type": identity_type, **body},
        domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
    )


def _utc(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("TEMPORAL_SPLIT_TIME_INVALID")
    return value.astimezone(UTC)
