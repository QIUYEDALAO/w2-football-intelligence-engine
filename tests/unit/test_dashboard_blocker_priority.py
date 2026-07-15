from __future__ import annotations

import json
from pathlib import Path

import pytest

from w2.dashboard.blocker_priority import prioritize_blockers

FIXTURE = Path(__file__).parents[1] / "fixtures" / "fme_blocker_precedence.json"


def test_primary_blocker_order_is_deterministic() -> None:
    first = prioritize_blockers(
        [
            "R4_1_FEATURE_HISTORY_INSUFFICIENT",
            "MODEL_FAIR_LINE_UNAVAILABLE",
            "MARKET_UNAVAILABLE",
        ]
    )
    second = prioritize_blockers(reversed(first["all_blockers"]))

    assert first["primary_blocker"] == "MARKET_UNAVAILABLE"
    assert first["primary_blocker_layer"] == "MARKET"
    assert second["primary_blocker"] == first["primary_blocker"]
    assert second["primary_blocker_layer"] == first["primary_blocker_layer"]


def test_all_blockers_are_preserved_without_duplicates() -> None:
    result = prioritize_blockers(
        ["NO_EDGE", "MODEL_FAIR_LINE_UNAVAILABLE", "NO_EDGE"]
    )

    assert result["primary_blocker"] == "FME_PROVENANCE_INCOMPLETE"
    assert result["primary_blocker_layer"] == "FME_PROVENANCE"
    assert result["all_blockers"] == ["NO_EDGE", "MODEL_FAIR_LINE_UNAVAILABLE"]


def test_feature_fallback_reason_remains_lower_priority_than_market() -> None:
    result = prioritize_blockers(
        ["R4_1_FEATURE_HISTORY_INSUFFICIENT", "MARKET_UNAVAILABLE"]
    )

    assert result["primary_blocker"] == "MARKET_UNAVAILABLE"
    assert result["primary_blocker_layer"] == "MARKET"


@pytest.mark.parametrize(
    "case",
    json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"],
    ids=lambda case: case["name"],
)
def test_sanitized_staging_blocker_regressions(case: dict[str, object]) -> None:
    result = prioritize_blockers(case["blockers"])

    assert result["primary_blocker"] == case["expected_primary"]
    assert result["primary_blocker_layer"] == case["expected_layer"]
