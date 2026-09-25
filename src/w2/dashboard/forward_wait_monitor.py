"""Read-only forward bias observation from settled, version-bound rows."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

MIN_DRIFT_N = 20
REALIZED = {"WIN": 1.0, "HALF_WIN": 0.5, "PUSH": 0.0, "HALF_LOSS": 0.0, "LOSS": 0.0}


def forward_bias_windows(
    rows: Sequence[tuple[datetime, Mapping[str, Any], str]],
    *,
    as_of: datetime,
) -> dict[str, Any]:
    """Observe success-probability bias, never fit or alter a calibration."""
    scored: list[tuple[datetime, float]] = []
    for evaluated_at, payload, settlement in rows:
        distribution = payload.get("model_settlement_distribution")
        if settlement not in REALIZED or not isinstance(distribution, Mapping):
            continue
        try:
            win = float(distribution["WIN"])
            half_win = float(distribution["HALF_WIN"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if not all(math.isfinite(value) and 0 <= value <= 1 for value in (win, half_win)):
            continue
        scored.append((evaluated_at, win + 0.5 * half_win - REALIZED[settlement]))
    result: dict[str, Any] = {"status": "INSUFFICIENT_FORWARD_SETTLEMENTS", "n": len(scored)}
    for days in (7, 30):
        window = [bias for at, bias in scored if as_of - timedelta(days=days) <= at <= as_of]
        result[f"n_{days}d"] = len(window)
        result[f"bias_{days}d"] = sum(window) / len(window) if len(window) >= MIN_DRIFT_N else None
    if result["bias_30d"] is not None:
        result["status"] = "OBSERVED_HUMAN_REVIEW_ONLY"
    return result
