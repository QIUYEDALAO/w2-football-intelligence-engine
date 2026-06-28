from __future__ import annotations

import pytest

from w2.analysis.market_movement import build_bookmaker_hypothesis

FORBIDDEN_HYPOTHESIS_TERMS = [
    "偏主队",
    "偏客队",
    "价值",
    "可买",
    "跟庄",
    "庄家开错",
    "诱盘确认",
    "照这个买",
]


def test_ready_hypothesis_is_unverified_and_has_alternatives() -> None:
    payload = build_bookmaker_hypothesis(
        market_movement={"status": "READY", "pattern": "ONE_WAY"},
        market_divergence={"status": "READY", "book_deeper_side": "HOME"},
    )

    assert payload["status"] == "READY"
    assert "未验证" in payload["label"]
    assert "未验证" in payload["hypothesis"]
    assert payload["alternative_explanations"]
    assert payload["sample_status"] == "观察中"
    assert payload["sample_count"] == 0
    assert payload["verified"] is False
    assert payload["direction_allowed"] is False
    assert "仅作观察" in payload["hypothesis"]
    assert "不给方向" in payload["hypothesis"]


def test_insufficient_timeline_does_not_form_strong_hypothesis() -> None:
    payload = build_bookmaker_hypothesis(
        market_movement={"status": "INSUFFICIENT"},
        market_divergence={"status": "INSUFFICIENT"},
    )

    assert payload["status"] == "INSUFFICIENT"
    assert payload["hypothesis"] == "盘口轨迹不足，暂不形成假设；仅作观察，不给方向。"
    assert payload["sample_count"] == 0


@pytest.mark.parametrize("deeper_side", ["HOME", "AWAY", "UNKNOWN"])
def test_hypothesis_text_avoids_directional_and_betting_claims(deeper_side: str) -> None:
    payload = build_bookmaker_hypothesis(
        market_movement={"status": "READY", "pattern": "JUMP_LINE"},
        market_divergence={"status": "READY", "book_deeper_side": deeper_side},
    )
    text = " ".join(
        [
            str(payload["label"]),
            str(payload["hypothesis"]),
            " ".join(payload["alternative_explanations"]),
        ]
    )

    assert "未验证" in text
    assert "仅作观察" in text
    assert "不给方向" in text
    assert payload["alternative_explanations"]
    assert payload["sample_count"] == 0
    assert payload["verified"] is False
    assert payload["direction_allowed"] is False
    for term in FORBIDDEN_HYPOTHESIS_TERMS:
        assert term not in text


def test_ready_home_and_away_hypotheses_use_neutral_market_structure_copy() -> None:
    home = build_bookmaker_hypothesis(
        market_movement={"status": "READY", "pattern": "ONE_WAY"},
        market_divergence={"status": "READY", "book_deeper_side": "HOME"},
    )
    away = build_bookmaker_hypothesis(
        market_movement={"status": "READY", "pattern": "ONE_WAY"},
        market_divergence={"status": "READY", "book_deeper_side": "AWAY"},
    )

    assert "市场主队侧盘口深于未校准规则盘" in home["hypothesis"]
    assert "市场客队侧盘口深于未校准规则盘" in away["hypothesis"]
    assert "偏主队" not in home["hypothesis"]
    assert "偏客队" not in away["hypothesis"]
