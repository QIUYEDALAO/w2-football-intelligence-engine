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


def test_formal_card_copy_localizes_prematch_blockers_and_formal_scoreline() -> None:
    card = (ROOT / "apps/web/src/components/RecommendationCard.tsx").read_text()

    assert 'FIXTURE_NOT_PREMATCH: "比赛已开赛或已完场"' in card
    assert 'source === "formal_simulation"' in card
    assert "未出正式推荐原因" in card


def test_dashboard_defaults_to_formal_first_upcoming_view() -> None:
    page = (ROOT / "apps/web/src/components/DashboardPage.tsx").read_text()

    assert 'useState<DashboardMode>("next36")' in page
    assert "sortFormalFirst(view.upcoming)" in page
    assert "其他比赛分析参考" in page
