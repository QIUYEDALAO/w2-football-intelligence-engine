from __future__ import annotations

from w2.analysis.market_movement import build_bookmaker_hypothesis


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


def test_insufficient_timeline_does_not_form_strong_hypothesis() -> None:
    payload = build_bookmaker_hypothesis(
        market_movement={"status": "INSUFFICIENT"},
        market_divergence={"status": "INSUFFICIENT"},
    )

    assert payload["status"] == "INSUFFICIENT"
    assert payload["hypothesis"] == "盘口轨迹不足，暂不形成假设；仅作观察，不给方向。"
    assert payload["sample_count"] == 0


def test_hypothesis_text_avoids_betting_direction_and_forbidden_claims() -> None:
    payload = build_bookmaker_hypothesis(
        market_movement={"status": "READY", "pattern": "JUMP_LINE"},
        market_divergence={"status": "READY", "book_deeper_side": "AWAY"},
    )
    text = " ".join(
        [
            str(payload["label"]),
            str(payload["hypothesis"]),
            " ".join(payload["alternative_explanations"]),
        ]
    )

    assert "未验证" in text
    assert "买" not in text
    assert "跟庄" not in text
    assert "诱盘确认" not in text
    assert "庄家开错" not in text

