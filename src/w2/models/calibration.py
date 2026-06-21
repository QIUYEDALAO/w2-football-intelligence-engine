from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CalibrationMethod(StrEnum):
    PLATT = "PLATT"
    ISOTONIC = "ISOTONIC"
    BETA = "BETA"
    DIRICHLET_MULTICLASS = "DIRICHLET_MULTICLASS"


@dataclass(frozen=True, kw_only=True)
class CalibrationArtifact:
    method: CalibrationMethod
    fitted_on: str
    parameters: dict[str, float]


def fit_calibration(
    rows: list[tuple[dict[str, float], str]],
    method: CalibrationMethod,
    *,
    fitted_on: str,
) -> CalibrationArtifact:
    if not rows:
        return CalibrationArtifact(method=method, fitted_on=fitted_on, parameters={"strength": 1.0})
    avg_confidence = sum(max(probabilities.values()) for probabilities, _ in rows) / len(rows)
    accuracy = sum(
        1.0
        for probabilities, actual in rows
        if max(probabilities.items(), key=lambda item: item[1])[0] == actual
    ) / len(rows)
    gap = avg_confidence - accuracy
    if method == CalibrationMethod.PLATT:
        strength = max(min(1.0 - gap * 0.35, 1.2), 0.8)
    elif method == CalibrationMethod.ISOTONIC:
        strength = max(min(1.0 - gap * 0.50, 1.25), 0.75)
    elif method == CalibrationMethod.BETA:
        strength = max(min(1.0 - gap * 0.25, 1.15), 0.85)
    else:
        strength = max(min(1.0 - gap * 0.40, 1.20), 0.80)
    return CalibrationArtifact(
        method=method,
        fitted_on=fitted_on,
        parameters={"strength": strength, "validation_gap": gap},
    )


def apply_calibration(
    probabilities: dict[str, float],
    artifact: CalibrationArtifact,
) -> dict[str, float]:
    strength = artifact.parameters["strength"]
    adjusted = {key: value**strength for key, value in probabilities.items()}
    total = sum(adjusted.values())
    return {key: value / total for key, value in adjusted.items()}
