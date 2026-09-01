from __future__ import annotations

import json

import pytest
from scripts.fit_v1_ah_goal_share_calibration import (
    _current_logit,
    _lambdas,
    _objective,
    _sigmoid,
    _validate_frozen_sources,
    fit,
)


def test_goal_share_fit_recovers_a_known_logit_transform() -> None:
    rows = []
    for index in range(20):
        row = {
            "home_for": 0.8 + index * 0.08,
            "home_against": 1.1,
            "away_for": 1.2,
            "away_against": 1.3,
        }
        home_goals = round(1000 * _sigmoid(0.10 + 0.80 * _current_logit(row)))
        row.update(goals_home=home_goals, goals_away=1000 - home_goals)
        rows.append(row)

    intercept, scale = fit(rows)
    assert intercept == pytest.approx(0.10, abs=0.01)
    assert scale == pytest.approx(0.80, abs=0.01)
    assert _objective(rows, (intercept, scale)) <= _objective(rows, (0.0, 1.0))


def test_candidate_preserves_totals_axis_exactly() -> None:
    row = {
        "home_for": 1.8,
        "home_against": 1.0,
        "away_for": 1.2,
        "away_against": 1.4,
        "goals_home": 2,
        "goals_away": 1,
    }
    baseline = _lambdas(row, "totals_only")
    candidate = _lambdas(row, "candidate", (0.05, 1.1))

    assert candidate[0] + candidate[1] == pytest.approx(baseline[0] + baseline[1], abs=1e-12)
    assert candidate[2] is False


def test_frozen_source_digest_mismatch_is_rejected(tmp_path) -> None:
    home_away = tmp_path / "home-away.csv"
    xg = tmp_path / "xg.csv"
    protocol = tmp_path / "protocol.json"
    home_away.write_text("frozen home-away", encoding="utf-8")
    xg.write_text("frozen xg", encoding="utf-8")
    protocol.write_text(
        json.dumps(
            {
                "data": {
                    "strict_pit_8659": {
                        "home_away_sha256": "wrong",
                        "xg_sha256": "wrong",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="frozen home_away_sha256 mismatch"):
        _validate_frozen_sources(home_away, xg, protocol)
