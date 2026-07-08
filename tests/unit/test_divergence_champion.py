from __future__ import annotations

from typing import Any

from w2.api.repository import ReadModelService
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


def test_repository_divergence_uses_r4_1_champion_when_artifact_available(
    monkeypatch: Any,
) -> None:
    service = ReadModelService()
    monkeypatch.setattr(service, "_market_timeline_payload", lambda _fixture_id: _timeline())
    card = _card("chinese_super_league")
    card["r4_1_calibrated"] = {
        "probabilities": {"HOME": 0.52, "DRAW": 0.25, "AWAY": 0.23},
        "fair_ah": -1.0,
    }

    service._attach_market_movement_fields(card)

    assert card["pricing_shadow"]["model_family"] == "R4_1_CALIBRATED"
    assert card["pricing_shadow"]["fair_ah"] == -1.0
    assert card["market_divergence"]["model_family"] == "R4_1_CALIBRATED"
    assert card["market_divergence"]["model_probabilities"]["HOME"] == 0.52
    assert card["market_divergence"]["direction_allowed"] is False


def test_repository_divergence_falls_back_when_r4_1_artifact_missing(
    monkeypatch: Any,
) -> None:
    service = ReadModelService()
    monkeypatch.setattr(service, "_market_timeline_payload", lambda _fixture_id: _timeline())
    card = _card("allsvenskan")

    service._attach_market_movement_fields(card)

    assert card["pricing_shadow"]["model_family"] == "FITTED_CALIBRATED"
    assert (
        card["pricing_shadow"]["model_family_fallback_reason"]
        == "R4_1_PROBABILITIES_MISSING"
    )
    assert card["market_divergence"]["model_family"] == "FITTED_CALIBRATED"
    assert (
        card["market_divergence"]["model_family_fallback_reason"]
        == "R4_1_PROBABILITIES_MISSING"
    )
    assert card["pricing_shadow"]["fair_ah"] == -0.25
    assert card["market_divergence"]["direction_allowed"] is False


def test_repository_divergence_keeps_premier_league_on_fitted(
    monkeypatch: Any,
) -> None:
    service = ReadModelService()
    monkeypatch.setattr(service, "_market_timeline_payload", lambda _fixture_id: _timeline())
    card = _card("premier_league")
    card["r4_1_calibrated"] = {
        "probabilities": {"HOME": 0.52, "DRAW": 0.25, "AWAY": 0.23},
        "fair_ah": -1.0,
    }

    service._attach_market_movement_fields(card)

    assert card["pricing_shadow"]["model_family"] == "FITTED_CALIBRATED"
    assert "model_family_fallback_reason" not in card["pricing_shadow"]
    assert card["market_divergence"]["model_family"] == "FITTED_CALIBRATED"
    assert card["pricing_shadow"]["fair_ah"] == -0.25


def _card(competition_id: str) -> dict[str, Any]:
    return {
        "fixture_id": "fixture-1",
        "competition_id": competition_id,
        "home_name": "Home",
        "away_name": "Away",
        "model_probabilities": {"one_x_two": {"HOME": 0.4, "DRAW": 0.3, "AWAY": 0.3}},
        "current_odds": {
            "ah": {
                "home_line": "-0.5",
                "away_line": "0.5",
                "home_price": 1.9,
                "away_price": 1.9,
            }
        },
        "pricing_shadow": {
            "fair_ah": -0.25,
            "market_ah": -0.5,
            "edge_ah": -0.25,
            "team_score": {"home": 0.6, "away": 0.4},
        },
    }


def _timeline() -> dict[str, Any]:
    return {
        "snapshots": [
            {
                "market": "ASIAN_HANDICAP",
                "checkpoint": "opening",
                "line": -0.5,
                "home_price": 1.9,
                "away_price": 1.9,
                "as_of": "2026-07-08T00:00:00Z",
            },
            {
                "market": "ASIAN_HANDICAP",
                "checkpoint": "lock",
                "line": -0.75,
                "home_price": 1.9,
                "away_price": 1.9,
                "as_of": "2026-07-08T02:00:00Z",
            },
        ]
    }
