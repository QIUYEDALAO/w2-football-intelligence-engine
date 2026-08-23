from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from w2.domain.canonical_serialization import HashDomain, canonical_sha256

CALIBRATION_SCHEMA_VERSION = "w2.factor_model_v2.calibration.v1"
CALIBRATION_PATH = Path("config/calibration/factor_model_v2.unfitted.json")


@lru_cache(maxsize=1)
def load_unfitted_factor_shadow_calibration() -> dict[str, Any]:
    path = _calibration_path()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != (
        CALIBRATION_SCHEMA_VERSION
    ):
        raise ValueError("FACTOR_SHADOW_CALIBRATION_SCHEMA_INVALID")
    if payload.get("status") != "UNFITTED" or payload.get("coefficients") != {}:
        raise ValueError("FACTOR_SHADOW_CALIBRATION_NOT_UNFITTED")
    if payload.get("admitted_for_historical_replay") is not False or payload.get(
        "admitted_for_forward_shadow"
    ) is not False:
        raise ValueError("FACTOR_SHADOW_CALIBRATION_ALREADY_ADMITTED")
    return {
        **payload,
        "artifact_sha256": canonical_sha256(
            payload,
            domain=HashDomain.PREMATCH_READ_MODEL_GENERIC,
        ),
    }


def _calibration_path() -> Path:
    candidates = (
        Path.cwd() / CALIBRATION_PATH,
        Path(__file__).resolve().parents[3] / CALIBRATION_PATH,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("FACTOR_SHADOW_CALIBRATION_NOT_FOUND")
