from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from w2.models.independent import artifact_hash
from w2.models.r4_1_features import (
    R4_1_TIME_DECAY_HALF_LIFE_DAYS,
    R4_1_WINDOW_MATCHES,
    r4_1_prediction_from_feature_rows,
)

R4_1_ARTIFACT_SCHEMA_VERSION = "r4_1.v1"
R4_1_SOURCE_EVAL_DOC = "docs/consolidation/W2_R4_1_MODEL_GAP_REDUCTION_EVAL_20260708.md"
DEFAULT_R4_1_ARTIFACT_DIR = Path("runtime/model_artifacts/r4_1")


@dataclass(frozen=True, kw_only=True)
class R4_1Artifact:
    schema_version: str
    competition_id: str
    coefficients: tuple[float, ...]
    feature_names: tuple[str, ...]
    temperature: float
    rho: float
    home_coefficients: dict[str, float]
    feature_spec: dict[str, Any]
    train_cutoff_utc: datetime
    fit_sample_count: int
    protocol_identity_check: str
    source_eval_doc: str
    artifact_hash: str
    artifact_version: str


@dataclass(frozen=True, kw_only=True)
class R4_1ArtifactLoadResult:
    artifacts: dict[str, R4_1Artifact]
    invalid_reasons: dict[str, str]


def r4_1_artifact_dir(root: Path | None = None) -> Path:
    configured = os.environ.get("W2_R4_1_ARTIFACT_DIR")
    if configured:
        return Path(configured)
    base = root or Path.cwd()
    return base / DEFAULT_R4_1_ARTIFACT_DIR


def build_r4_1_artifact_payload(
    *,
    competition_id: str,
    coefficients: Sequence[float],
    feature_names: Sequence[str],
    temperature: float,
    rho: float,
    train_cutoff_utc: datetime,
    fit_sample_count: int,
    protocol_identity_check: str,
    artifact_version: str = "v1",
) -> dict[str, Any]:
    home_coefficients = {
        name.removeprefix("home_field__"): float(value)
        for name, value in zip(feature_names, coefficients, strict=False)
        if name.startswith("home_field__")
    }
    payload: dict[str, Any] = {
        "schema_version": R4_1_ARTIFACT_SCHEMA_VERSION,
        "competition_id": competition_id,
        "coefficients": {
            name: float(value)
            for name, value in zip(feature_names, coefficients, strict=False)
        },
        "temperature": float(temperature),
        "rho": float(rho),
        "home_coefficients": home_coefficients,
        "feature_spec": {
            "window": R4_1_WINDOW_MATCHES,
            "half_life_days": R4_1_TIME_DECAY_HALF_LIFE_DAYS,
            "opponent_adjusted": True,
        },
        "train_cutoff_utc": _iso_utc(train_cutoff_utc),
        "fit_sample_count": int(fit_sample_count),
        "protocol_identity_check": protocol_identity_check,
        "source_eval_doc": R4_1_SOURCE_EVAL_DOC,
        "artifact_version": artifact_version,
    }
    payload["artifact_hash"] = compute_r4_1_artifact_hash(payload)
    return payload


def compute_r4_1_artifact_hash(payload: Mapping[str, Any]) -> str:
    stripped = {key: value for key, value in payload.items() if key != "artifact_hash"}
    return artifact_hash(stripped)


def load_r4_1_artifacts(
    artifact_dir: Path,
    *,
    now: datetime | None = None,
) -> R4_1ArtifactLoadResult:
    if not artifact_dir.exists():
        return R4_1ArtifactLoadResult(artifacts={}, invalid_reasons={})
    selected: dict[str, tuple[Path, str]] = {}
    invalid: dict[str, str] = {}
    for path in sorted(artifact_dir.glob("*.json")):
        match = re.match(r"(?P<competition>.+)\.(?P<version>v\d+)\.json$", path.name)
        if match is None:
            invalid[path.stem] = "R4_1_ARTIFACT_INVALID_NAME"
            continue
        competition_id = match.group("competition")
        version = match.group("version")
        existing = selected.get(competition_id)
        if existing is None or _version_number(version) > _version_number(existing[1]):
            selected[competition_id] = (path, version)
    artifacts: dict[str, R4_1Artifact] = {}
    for competition_id, (path, version) in selected.items():
        try:
            artifact = parse_r4_1_artifact(
                json.loads(path.read_text(encoding="utf-8")),
                artifact_version=version,
                now=now,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            invalid[competition_id] = "R4_1_ARTIFACT_INVALID"
            continue
        artifacts[competition_id] = artifact
    return R4_1ArtifactLoadResult(artifacts=artifacts, invalid_reasons=invalid)


def parse_r4_1_artifact(
    payload: Mapping[str, Any],
    *,
    artifact_version: str | None = None,
    now: datetime | None = None,
) -> R4_1Artifact:
    if payload.get("schema_version") != R4_1_ARTIFACT_SCHEMA_VERSION:
        raise ValueError("invalid schema")
    expected_hash = str(payload.get("artifact_hash") or "")
    if expected_hash != compute_r4_1_artifact_hash(payload):
        raise ValueError("invalid artifact hash")
    cutoff = _parse_utc(str(payload["train_cutoff_utc"]))
    current = now or datetime.now(UTC)
    if cutoff >= current:
        raise ValueError("artifact train cutoff is not before now")
    coefficients_payload = payload["coefficients"]
    if not isinstance(coefficients_payload, Mapping):
        raise ValueError("invalid coefficients")
    feature_names = tuple(str(key) for key in coefficients_payload)
    coefficients = tuple(float(coefficients_payload[key]) for key in feature_names)
    return R4_1Artifact(
        schema_version=str(payload["schema_version"]),
        competition_id=str(payload["competition_id"]),
        coefficients=coefficients,
        feature_names=feature_names,
        temperature=float(payload["temperature"]),
        rho=float(payload["rho"]),
        home_coefficients={
            str(key): float(value)
            for key, value in dict(payload.get("home_coefficients") or {}).items()
        },
        feature_spec=dict(payload["feature_spec"]),
        train_cutoff_utc=cutoff,
        fit_sample_count=int(payload["fit_sample_count"]),
        protocol_identity_check=str(payload["protocol_identity_check"]),
        source_eval_doc=str(payload["source_eval_doc"]),
        artifact_hash=expected_hash,
        artifact_version=artifact_version or str(payload.get("artifact_version") or "v1"),
    )


def predict_r4_1_from_artifact(
    artifact: R4_1Artifact,
    *,
    home_row: Sequence[float],
    away_row: Sequence[float],
) -> dict[str, Any]:
    prediction = r4_1_prediction_from_feature_rows(
        home_row=home_row,
        away_row=away_row,
        coefficients=artifact.coefficients,
        rho=artifact.rho,
        temperature=artifact.temperature,
    )
    return {
        "probabilities": prediction.probabilities,
        "fair_ah": prediction.fair_ah,
        "artifact_hash": artifact.artifact_hash,
        "artifact_version": artifact.artifact_version,
    }


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _version_number(value: str) -> int:
    return int(value.removeprefix("v") or "0")
