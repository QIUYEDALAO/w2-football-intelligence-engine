"""AH/OU 软最大值公式 + 特征构造 单测（核心逻辑手算 + 参数维度校验）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from w2.strategy.ah_ou_features import build_features
from w2.strategy.ah_ou_softmax import (
    ah_home_cover_p,
    ah_select,
    load_ah_model,
    load_ou_model,
    ou_factor_share,
    ou_select,
)


def _snapshot(xgf: float, xga: float) -> dict:
    return {"rolling_xg_for": xgf, "rolling_xg_against": xga}


def _meetings(diffs: list[int], kickoff: datetime, side: str = "AWAY") -> list[dict]:
    rows = []
    for index, diff in enumerate(diffs, start=1):
        rows.append(
            {
                "goals_for": max(diff, 0) + 1 if diff >= 0 else 1,
                "goals_against": 1 if diff >= 0 else 1 - diff,
                "kickoff_at": (kickoff - timedelta(days=10 * index)).isoformat(),
                "team_side": side,
            }
        )
    return rows


KICKOFF = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


def test_f9_score_and_f6_shrunk_hand_calc() -> None:
    features = build_features(
        home_snapshot=_snapshot(1.2, 0.8),
        away_snapshot=_snapshot(0.8, 1.2),
        meetings=_meetings([1, -1, 1], KICKOFF),
        kickoff=KICKOFF,
    )
    assert features["f9_score"] == pytest.approx(((1.2 - 0.8) - (0.8 - 1.2)) / 2)
    assert features["f9_home_xgf"] == 1.2
    assert features["f6_n"] == 3
    # diffs = [1, -1, 1] -> sum=1 -> f6_raw = clip(1/3/2)=1/6
    assert features["f6_score"] == pytest.approx(1 / 6)
    assert features["f6_shrunk"] == pytest.approx((1 / 6) * 3 / 8)


def test_build_features_empty_h2h_raises() -> None:
    with pytest.raises(ValueError, match="EMPTY_H2H"):
        build_features(
            home_snapshot=_snapshot(1.2, 0.8),
            away_snapshot=_snapshot(0.8, 1.2),
            meetings=[],
            kickoff=KICKOFF,
        )


def test_ah_side_follows_market_and_selected() -> None:
    features = build_features(
        home_snapshot=_snapshot(1.2, 0.8),
        away_snapshot=_snapshot(0.8, 1.2),
        meetings=_meetings([1, 1, 1], KICKOFF),
        kickoff=KICKOFF,
    )
    # home_odds < away_odds -> q >= 0.5 -> HOME
    home_fav = ah_select(features, home_line=-0.5, home_odds=1.8, away_odds=2.2)
    assert home_fav["side"] == "HOME"
    assert home_fav["market_home_cover_p"] == pytest.approx((1 / 1.8) / ((1 / 1.8) + (1 / 2.2)))
    # away_odds < home_odds -> q < 0.5 -> AWAY
    away_fav = ah_select(features, home_line=-0.5, home_odds=2.2, away_odds=1.8)
    assert away_fav["side"] == "AWAY"


def test_ah_home_cover_p_in_unit_interval() -> None:
    features = build_features(
        home_snapshot=_snapshot(1.2, 0.8),
        away_snapshot=_snapshot(0.8, 1.2),
        meetings=_meetings([1, -1, 1], KICKOFF),
        kickoff=KICKOFF,
    )
    p = ah_home_cover_p(features, home_line=-0.5)
    assert 0.0 <= p <= 1.0


def test_ou_factor_share_and_select_bounds() -> None:
    features = build_features(
        home_snapshot=_snapshot(1.2, 0.8),
        away_snapshot=_snapshot(0.8, 1.2),
        meetings=_meetings([1, 1, -1], KICKOFF),
        kickoff=KICKOFF,
    )
    share = ou_factor_share(features, line=2.5)
    assert 0.0 <= share <= 1.0
    selection = ou_select(features, line=2.5, over_odds=1.9, under_odds=1.9)
    assert selection["market_over_q"] == pytest.approx(0.5)
    assert selection["edge"] == pytest.approx(share - 0.5)


def test_model_params_dimensions_consistent() -> None:
    ah = load_ah_model()
    ou = load_ou_model()
    assert len(ah["feature_order"]) == len(ah["scaler_mean"]) == len(ah["scaler_scale"]) == 14
    assert (
        len(ah["softmax_intercept"]) == len(ah["softmax_coefficients"]) == len(ah["classes"]) == 9
    )
    assert all(len(coef) == 14 for coef in ah["softmax_coefficients"])
    assert len(ou["feature_order"]) == len(ou["scaler_mean"]) == len(ou["scaler_scale"]) == 22
    assert (
        len(ou["softmax_intercept"]) == len(ou["softmax_coefficients"]) == len(ou["classes"]) == 9
    )
    assert all(len(coef) == 22 for coef in ou["softmax_coefficients"])
