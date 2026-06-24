from __future__ import annotations

import pytest

from w2.strategy.score_scenarios import build_score_scenarios, score_direction


def test_score_direction_buckets_scores() -> None:
    assert score_direction((2, 1)) == "HOME"
    assert score_direction((1, 1)) == "DRAW"
    assert score_direction((0, 2)) == "AWAY"


def test_skip_emits_no_scores() -> None:
    summary = build_score_scenarios(
        score_matrix={(1, 1): 0.4, (2, 1): 0.3},
        decision="SKIP",
        direction="HOME",
    )

    assert summary.direction is None
    assert summary.global_top_scores == []
    assert summary.direction_consistent_scores == []


def test_main_direction_consistent_scores_avoid_global_one_one_trap() -> None:
    summary = build_score_scenarios(
        score_matrix={
            (1, 1): 0.30,
            (2, 1): 0.18,
            (1, 0): 0.12,
            (0, 1): 0.10,
            (2, 2): 0.08,
        },
        decision="MAIN",
        direction="HOME",
        limit=2,
    )

    assert summary.global_top_scores[0].score == "1-1"
    assert [row.score for row in summary.direction_consistent_scores] == ["2-1", "1-0"]
    assert all(row.home_score > row.away_score for row in summary.direction_consistent_scores)
    assert sum(row.conditional_probability or 0 for row in summary.direction_consistent_scores) == (
        pytest.approx(1.0)
    )


def test_main_requires_direction_and_direction_probability_mass() -> None:
    with pytest.raises(ValueError, match="direction is required"):
        build_score_scenarios(score_matrix={(1, 0): 1.0}, decision="MAIN", direction=None)
    with pytest.raises(ValueError, match="direction bucket has no probability mass"):
        build_score_scenarios(score_matrix={(1, 0): 1.0}, decision="MAIN", direction="AWAY")
