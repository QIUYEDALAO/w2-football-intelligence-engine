from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, kw_only=True)
class DriftDiagnostic:
    name: str
    value: float
    status: str
    read_only: bool = True
    action: str = "DIAGNOSE_ONLY"


def drift_diagnostics(inputs: dict[str, float]) -> list[DriftDiagnostic]:
    return [
        DriftDiagnostic(
            name="prediction_distribution_drift",
            value=inputs.get("prediction", 0.0),
            status="WATCH",
        ),
        DriftDiagnostic(
            name="probability_calibration_drift",
            value=inputs.get("calibration", 0.0),
            status="WATCH",
        ),
        DriftDiagnostic(
            name="feature_missingness_drift",
            value=inputs.get("missingness", 0.0),
            status="WATCH",
        ),
        DriftDiagnostic(
            name="bookmaker_coverage_drift",
            value=inputs.get("bookmaker", 0.0),
            status="WATCH",
        ),
        DriftDiagnostic(
            name="market_independent_divergence_drift",
            value=inputs.get("divergence", 0.0),
            status="WATCH",
        ),
    ]


def drift_report(inputs: dict[str, float]) -> dict[str, Any]:
    diagnostics = drift_diagnostics(inputs)
    return {
        "diagnostics": [item.__dict__ for item in diagnostics],
        "auto_tuning": False,
        "auto_model_replacement": False,
        "auto_gate_change": False,
    }
