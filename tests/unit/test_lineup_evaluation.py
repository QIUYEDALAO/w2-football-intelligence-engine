from __future__ import annotations

import pytest

from w2.lineups.evaluation import PairedEvaluationRow, evaluate_market_adjustment


def test_lineup_evaluation_fails_closed_when_sample_gate_is_missing() -> None:
    gate = evaluate_market_adjustment([], bootstrap_samples=10)
    assert not gate.enabled
    assert "INSUFFICIENT_VALIDATION_FIXTURES" in gate.blockers


def test_lineup_evaluation_uses_chronological_validation_and_enables_real_gain() -> None:
    rows = [
        PairedEvaluationRow(
            fixture_id=f"f-{index}",
            competition_id=f"c-{index % 3}",
            kickoff_epoch=index,
            baseline_probability=0.55,
            candidate_probability=0.90,
            outcome=1,
            baseline_rps=0.20,
            candidate_rps=0.10,
        )
        for index in range(30)
    ]
    gate = evaluate_market_adjustment(
        rows,
        bootstrap_samples=100,
        minimum_samples=9,
        minimum_competitions=3,
    )
    assert gate.enabled
    assert gate.sample_count == 9
    assert gate.log_loss_ci_high is not None and gate.log_loss_ci_high < 0


def test_lineup_evaluation_rejects_non_positive_bootstrap_samples() -> None:
    row = PairedEvaluationRow(
        fixture_id="f-1", competition_id="c-1", kickoff_epoch=1,
        baseline_probability=0.5, candidate_probability=0.5, outcome=1,
        baseline_rps=0.2, candidate_rps=0.2,
    )
    with pytest.raises(ValueError, match="positive sample count"):
        evaluate_market_adjustment(
            [row], bootstrap_samples=0, minimum_samples=0, minimum_competitions=0
        )
