from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.fit_v1_ah_component_share_calibration import (
    BOOTSTRAP_LOWER_PROBABILITY,
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED_BASE,
    BOOTSTRAP_UPPER_PROBABILITY,
    PARAMETER_BOUNDS,
    _eta,
    _lambdas,
    fit,
)
from scripts.fit_v1_ah_goal_share_calibration import _sigmoid

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "docs/operations/V1_AH_COMPONENT_SHARE_CALIBRATION_PREREGISTRATION_20260901.json"


def test_runner_constants_match_frozen_protocol() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    acceptance = protocol["acceptance"]
    bounds = protocol["candidate"]["bounds"]

    assert BOOTSTRAP_RESAMPLES == acceptance["bootstrap_resamples"]
    assert BOOTSTRAP_SEED_BASE == acceptance["bootstrap_seed_base"]
    assert BOOTSTRAP_LOWER_PROBABILITY == acceptance["bootstrap_lower_probability"]
    assert BOOTSTRAP_UPPER_PROBABILITY == acceptance["bootstrap_upper_probability"]
    assert PARAMETER_BOUNDS == tuple(
        tuple(bounds[name])
        for name in ("home_adjustment", "attack_adjustment", "defence_adjustment")
    )


def test_component_share_fit_recovers_known_adjustments() -> None:
    expected = (0.30, -0.20, 0.45)
    rows = []
    for index in range(60):
        row = {
            "home_for": 0.8 + (index % 7) * 0.20,
            "home_against": 0.7 + ((index * 5) % 6) * 0.18,
            "away_for": 0.9 + ((index * 3) % 7) * 0.15,
            "away_against": 0.8 + ((index * 2) % 5) * 0.22,
        }
        home_goals = round(10_000 * _sigmoid(_eta(row, expected)))
        row.update(goals_home=home_goals, goals_away=10_000 - home_goals)
        rows.append(row)

    actual = fit(rows)
    assert actual == pytest.approx(expected, abs=0.01)


def test_zero_adjustments_equal_the_totals_only_baseline() -> None:
    row = {
        "home_for": 1.8,
        "home_against": 1.0,
        "away_for": 1.2,
        "away_against": 1.4,
        "goals_home": 2,
        "goals_away": 1,
    }
    baseline = _lambdas(row, "totals_only")
    candidate = _lambdas(row, "candidate", (0.0, 0.0, 0.0))

    assert candidate[:2] == pytest.approx(baseline[:2], abs=1e-12)
    assert candidate[2] is False


def test_lower_parameter_bounds_preserve_component_direction() -> None:
    baseline = {
        "home_for": 1.2,
        "home_against": 1.1,
        "away_for": 1.2,
        "away_against": 1.1,
        "goals_home": 1,
        "goals_away": 1,
    }
    stronger_attack = {**baseline, "home_for": 1.3}
    weaker_away_defence = {**baseline, "away_against": 1.2}
    parameters = (-1.0, -1.0, -1.0)

    reference = _lambdas(baseline, "candidate", parameters)[0]
    assert _lambdas(stronger_attack, "candidate", parameters)[0] > reference
    assert _lambdas(weaker_away_defence, "candidate", parameters)[0] > reference
