"""Operational pause of current recommendations, independent of fact ingestion."""

from __future__ import annotations

import os


def current_recommendations_paused() -> bool:
    # Unknown configuration also closes the current write/read/send outlets.
    return os.environ.get("W2_CURRENT_RECOMMENDATIONS_PAUSED", "false").strip().lower() != "false"


def require_current_recommendations_running() -> None:
    if current_recommendations_paused():
        raise RuntimeError("CURRENT_RECOMMENDATIONS_PAUSED")
