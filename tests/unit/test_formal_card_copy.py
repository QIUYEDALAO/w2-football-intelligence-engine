from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_formal_card_copy_does_not_surface_performance_terms() -> None:
    card = (ROOT / "apps/web/src/components/RecommendationCard.tsx").read_text()

    for forbidden in [
        "命中率",
        "赢盘比例",
        "收益率",
        "hit rate",
        "win rate",
        "ROI",
    ]:
        assert forbidden not in card

    assert "样本统计暂不展示" in card
