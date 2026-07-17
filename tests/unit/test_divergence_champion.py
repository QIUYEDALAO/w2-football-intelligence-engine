from __future__ import annotations

from w2.models.divergence_champion import (
    DivergenceModelFamily,
    divergence_model_family_for,
    select_divergence_champion_probabilities,
)


def test_r4_1b_adopts_only_reviewed_league_champions() -> None:
    assert divergence_model_family_for("bundesliga") == DivergenceModelFamily.R4_1_CALIBRATED
    assert (
        divergence_model_family_for("chinese_super_league")
        == DivergenceModelFamily.R4_1_CALIBRATED
    )
    assert divergence_model_family_for("allsvenskan") == DivergenceModelFamily.R4_1_CALIBRATED

    assert (
        divergence_model_family_for("brasileirao_serie_a")
        == DivergenceModelFamily.FITTED_CALIBRATED
    )
    assert divergence_model_family_for("premier_league") == DivergenceModelFamily.FITTED_CALIBRATED
    assert divergence_model_family_for(None) == DivergenceModelFamily.FITTED_CALIBRATED


def test_select_divergence_champion_uses_r4_1_when_adopted() -> None:
    fitted = {"HOME": 0.4, "DRAW": 0.3, "AWAY": 0.3}
    r4_1 = {"HOME": 0.46, "DRAW": 0.27, "AWAY": 0.27}

    selection = select_divergence_champion_probabilities(
        competition_id="chinese_super_league",
        fitted_calibrated=fitted,
        r4_1_calibrated=r4_1,
    )

    assert selection.family == DivergenceModelFamily.R4_1_CALIBRATED
    assert selection.probabilities == r4_1
    assert selection.fallback_reason is None


def test_select_divergence_champion_fails_closed_to_fitted_when_r4_1_missing() -> None:
    fitted = {"HOME": 0.4, "DRAW": 0.3, "AWAY": 0.3}

    selection = select_divergence_champion_probabilities(
        competition_id="allsvenskan",
        fitted_calibrated=fitted,
        r4_1_calibrated=None,
    )

    assert selection.family == DivergenceModelFamily.FITTED_CALIBRATED
    assert selection.probabilities == fitted
    assert selection.fallback_reason == "R4_1_PROBABILITIES_MISSING"


def test_select_divergence_champion_keeps_worsened_leagues_on_fitted() -> None:
    fitted = {"HOME": 0.4, "DRAW": 0.3, "AWAY": 0.3}
    r4_1 = {"HOME": 0.46, "DRAW": 0.27, "AWAY": 0.27}

    selection = select_divergence_champion_probabilities(
        competition_id="brasileirao_serie_a",
        fitted_calibrated=fitted,
        r4_1_calibrated=r4_1,
    )

    assert selection.family == DivergenceModelFamily.FITTED_CALIBRATED
    assert selection.probabilities == fitted
    assert selection.fallback_reason is None
