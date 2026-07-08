from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from w2.api.repository import ReadModelService
from w2.models.divergence_champion import (
    DivergenceModelFamily,
    divergence_model_family_for,
    select_divergence_champion_probabilities,
)
from w2.models.r4_1_artifacts import build_r4_1_artifact_payload


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


def test_brasileirao_guard_stays_off_r4_1_after_failed_eval() -> None:
    # W2_R4_1_MODEL_GAP_REDUCTION_EVAL_20260708.md:
    # brasileirao worsened (+0.0538 -> +0.0550), so it must not be adopted.
    assert (
        divergence_model_family_for("brasileirao_serie_a")
        == DivergenceModelFamily.FITTED_CALIBRATED
    )


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


def test_repository_divergence_loads_r4_1_artifact_when_feature_rows_available(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    _write_artifact(tmp_path, "chinese_super_league")
    service = ReadModelService(r4_1_artifact_root=tmp_path)
    monkeypatch.setattr(service, "_market_timeline_payload", lambda _fixture_id: _timeline())
    card = _card("chinese_super_league")
    card["r4_1_feature_rows"] = {
        "home": [1.0, 1.0, 1.2, 1.1, 0.15, 1.0],
        "away": [1.0, 0.0, 0.9, 1.0, -0.15, 0.0],
    }

    service._attach_market_movement_fields(card)

    shadow = card["pricing_shadow"]
    divergence = card["market_divergence"]
    assert shadow["model_family"] == "R4_1_CALIBRATED"
    assert "model_family_fallback_reason" not in shadow
    assert abs(sum(shadow["model_probabilities"].values()) - 1.0) < 1e-9
    assert shadow["artifact_hash"]
    assert shadow["artifact_version"] == "v1"
    assert divergence["artifact_hash"] == shadow["artifact_hash"]
    assert divergence["model_family"] == "R4_1_CALIBRATED"
    assert divergence["direction_allowed"] is False


def test_repository_divergence_falls_back_when_r4_1_history_is_insufficient(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    _write_artifact(tmp_path, "allsvenskan")
    service = ReadModelService(r4_1_artifact_root=tmp_path)
    monkeypatch.setattr(service, "_market_timeline_payload", lambda _fixture_id: _timeline())
    card = _card("allsvenskan")

    service._attach_market_movement_fields(card)

    assert card["pricing_shadow"]["model_family"] == "FITTED_CALIBRATED"
    assert (
        card["pricing_shadow"]["model_family_fallback_reason"]
        == "R4_1_FEATURE_HISTORY_INSUFFICIENT"
    )
    assert card["market_divergence"]["model_family"] == "FITTED_CALIBRATED"
    assert (
        card["market_divergence"]["model_family_fallback_reason"]
        == "R4_1_FEATURE_HISTORY_INSUFFICIENT"
    )


def test_repository_divergence_falls_back_when_r4_1_artifact_hash_is_invalid(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    path = _write_artifact(tmp_path, "allsvenskan")
    payload = path.read_text(encoding="utf-8").replace("artifact_hash", "artifact_hash_broken")
    path.write_text(payload, encoding="utf-8")
    service = ReadModelService(r4_1_artifact_root=tmp_path)
    monkeypatch.setattr(service, "_market_timeline_payload", lambda _fixture_id: _timeline())
    card = _card("allsvenskan")
    card["r4_1_feature_rows"] = {
        "home": [1.0, 1.0, 1.2, 1.1, 0.15, 1.0],
        "away": [1.0, 0.0, 0.9, 1.0, -0.15, 0.0],
    }

    service._attach_market_movement_fields(card)

    assert card["pricing_shadow"]["model_family"] == "FITTED_CALIBRATED"
    assert (
        card["pricing_shadow"]["model_family_fallback_reason"]
        == "R4_1_ARTIFACT_INVALID"
    )
    assert card["market_divergence"]["direction_allowed"] is False


def test_repository_divergence_falls_back_when_r4_1_artifact_missing(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    service = ReadModelService(r4_1_artifact_root=tmp_path)
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


def _write_artifact(path: Path, competition_id: str) -> Path:
    payload = build_r4_1_artifact_payload(
        competition_id=competition_id,
        coefficients=(0.05, 0.12, 0.2, 0.14, 0.3, 0.08),
        feature_names=(
            "intercept",
            "home_field",
            "attack_xg_for",
            "opponent_xg_against",
            "elo_gap",
            f"home_field__{competition_id}",
            "dixon_coles_rho=-0.03",
        ),
        temperature=0.96,
        rho=-0.03,
        train_cutoff_utc=datetime(2026, 1, 1, tzinfo=UTC),
        fit_sample_count=250,
        protocol_identity_check="PASS",
    )
    target = path / f"{competition_id}.v1.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target
