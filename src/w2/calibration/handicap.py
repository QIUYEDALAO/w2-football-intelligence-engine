from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

HANDICAP_CALIBRATION_MODEL = "linear_supremacy_to_ah_delta.v1"
UNVALIDATED_VERSION = "UNVALIDATED"


@dataclass(frozen=True, kw_only=True)
class HandicapCalibrationInput:
    sample_size: int
    all_validation_checks_passed: bool
    included_rows: list[dict[str, Any]]
    generated_at: datetime | None = None
    n_min: int = 200


def build_handicap_calibration(inputs: HandicapCalibrationInput) -> dict[str, Any]:
    if inputs.sample_size < inputs.n_min:
        return _unvalidated("INSUFFICIENT_SAMPLE")
    if not inputs.all_validation_checks_passed:
        return _unvalidated("VALIDATION_GATE_FAILED")
    params = _fit_linear_scale(inputs.included_rows)
    generated_at = (inputs.generated_at or datetime.now(UTC)).astimezone(UTC)
    artifact = {
        "calibration_version": _candidate_version(params, inputs.sample_size),
        "status": "CANDIDATE_NOT_RUNTIME_ENABLED",
        "model": {
            "name": HANDICAP_CALIBRATION_MODEL,
            "trained_at": generated_at.isoformat().replace("+00:00", "Z"),
            "sample_size": inputs.sample_size,
        },
        "params": params,
        "runtime_enabled": False,
        "formal_enabled": False,
        "candidate_enabled": False,
        "beats_market": False,
    }
    return artifact


def _unvalidated(status: str) -> dict[str, Any]:
    return {
        "calibration_version": UNVALIDATED_VERSION,
        "status": status,
        "model": None,
        "params": None,
    }


def _fit_linear_scale(rows: list[dict[str, Any]]) -> dict[str, float]:
    pairs: list[tuple[float, float]] = []
    for row in rows:
        fair = _float_or_none(row.get("fair_ah"))
        market = _float_or_none(row.get("market_ah"))
        score_delta = _float_or_none(row.get("score_delta"))
        if fair is None or market is None or score_delta is None:
            continue
        pairs.append((score_delta, fair - market))
    if not pairs:
        return {"intercept": 0.0, "scale": 0.0}
    mean_x = sum(x for x, _y in pairs) / len(pairs)
    mean_y = sum(y for _x, y in pairs) / len(pairs)
    denominator = sum((x - mean_x) ** 2 for x, _y in pairs)
    if denominator == 0:
        scale = 0.0
    else:
        scale = sum((x - mean_x) * (y - mean_y) for x, y in pairs) / denominator
    intercept = mean_y - scale * mean_x
    return {"intercept": round(intercept, 6), "scale": round(scale, 6)}


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _candidate_version(params: dict[str, float], sample_size: int) -> str:
    payload = {"model": HANDICAP_CALIBRATION_MODEL, "params": params, "sample_size": sample_size}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
    return f"AH_CALIBRATION_CANDIDATE_{digest}"
