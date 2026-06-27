from __future__ import annotations

from typing import Any

PRICING_SHADOW_VERSION = "w2.s1.shadow.v1"
UNCALIBRATED_STATUS = "RULE_BASED_UNCALIBRATED"


def build_pricing_shadow(
    *,
    fixture_id: str,
    model_probabilities: dict[str, Any] | None,
    market_probabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model_ready = bool(model_probabilities)
    market_ready = bool(market_probabilities)
    return {
        "fixture_id": fixture_id,
        "status": UNCALIBRATED_STATUS,
        "model_version": PRICING_SHADOW_VERSION,
        "calibration_version": "UNVALIDATED",
        "factors": _factors(
            model_ready=model_ready,
            market_ready=market_ready,
        ),
        "fair_ah": None,
        "fair_ou": None,
        "market_ah": None,
        "market_ou": None,
        "edge_ah": None,
        "edge_ou": None,
        "coverage": {
            "model_probabilities": model_ready,
            "market_probabilities": market_ready,
            "fair_line": False,
            "edge": False,
        },
        "asof_market_snapshot_id": None,
        "devig_method": None,
        "settlement_outcome": None,
        "beats_market": False,
    }


def _factors(*, model_ready: bool, market_ready: bool) -> list[dict[str, Any]]:
    return [
        {
            "id": "model_probabilities",
            "side": "INDEPENDENT_MODEL",
            "weight": 0.0,
            "score": 1.0 if model_ready else 0.0,
            "status": "READY" if model_ready else "MISSING",
        },
        {
            "id": "market_probabilities",
            "side": "MARKET_BASELINE",
            "weight": 0.0,
            "score": 1.0 if market_ready else 0.0,
            "status": "READY" if market_ready else "MISSING",
        },
        {
            "id": "s2_calibration_gate",
            "side": "GATE",
            "weight": 0.0,
            "score": 0.0,
            "status": "NOT_EVALUATED",
        },
    ]
