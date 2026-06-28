from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_frontend_ah_gate_requires_validated_beats_market() -> None:
    helper = read("apps/web/src/lib/pricingDisplay.ts")
    card = read("apps/web/src/components/RecommendationCard.tsx")

    assert "shadow.beats_market !== true" in helper
    assert "hasValidatedAhCalibration(shadow)" in card
    assert "return \"WATCH\";" in card
    assert "shouldHideDirectionalCopy(match, verdict)" in card


def test_uncalibrated_ah_copy_does_not_emit_directional_edge() -> None:
    card = read("apps/web/src/components/RecommendationCard.tsx")
    normalize = read("apps/web/src/lib/normalize.ts")

    assert "未校准，不作为方向判断" in card
    assert "本场无可靠让球倾向" in card
    assert "directionalTotals: !lowInfo" in card
    assert "大小球 ${line} 两侧" in normalize
    assert "让球主市场：偏主队" not in card
    assert "让球主市场：偏客队" not in card
    assert "我们比市场更看主队" not in card
    assert "市场让得更深" not in card


def test_bookmaker_intent_is_labeled_as_unverified_hypothesis() -> None:
    odds_mini = read("apps/web/src/components/OddsMovementMini.tsx")
    intent_line = read("apps/web/src/components/BookmakerIntentLine.tsx")

    assert "盘口假设 · 未验证" in odds_mini
    assert "盘口轨迹不足" in odds_mini
    assert "未校准，仅作观察" in odds_mini
    assert "不显示命中率" in odds_mini
    assert "庄家意图" not in odds_mini
    assert "盘口假设 · 未验证" in intent_line
    assert "庄家意图" not in intent_line


def test_score_display_uses_index_scale_not_raw_scores() -> None:
    card = read("apps/web/src/components/RecommendationCard.tsx")

    assert "独立评分指数，仅用于两队相对比较" in card
    assert "中性因子不偏向任何一方" in card
    assert "scoreIndexValue" in card
    assert "value * 100).toFixed(1)" not in card
    assert "胜率" not in card


def test_ah_display_uses_home_perspective_sign_convention() -> None:
    helper = read("apps/web/src/lib/pricingDisplay.ts")
    normalize = read("apps/web/src/lib/normalize.ts")

    assert "numeric < 0 ? `主 -" in helper
    assert ": `客 -" in helper
    assert "formatSignedLine(-numeric)" in helper
    assert "formatAhSideLines(ah.line ?? ah.home_line)" in normalize
