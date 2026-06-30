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
    assert 'AH_EV_BELOW_FORMAL_THRESHOLD: "让球结算期望未达正式推荐阈值"' in card
    assert 'MISSING_AH_SETTLEMENT_DISTRIBUTION: "缺少让球结算分布"' in card
    assert 'AH_MARKET_LINE_SIDE_MISMATCH: "全场让球双边盘口方向不一致"' in card
    assert 'source === "formal_simulation"' in card
    assert "未出正式推荐原因" in card
    assert "模拟中位比分参考，不是推荐比分：" in card
    assert "最可能：" not in card
    assert "总进球≥" not in card
    assert "让球结算关键比分" not in card
    assert "全赢" not in card
    assert "半输" not in card
    assert "全输" not in card
    assert "推荐比分" not in card.replace("不是推荐比分", "")


def test_frontend_normalizes_scoreline_reference_payload() -> None:
    api = (ROOT / "apps/web/src/lib/dashboardApi.ts").read_text()

    assert "function normalizeScorelineReference" in api
    assert "scoreline_reference: normalizeScorelineReference(record.scoreline_reference)" in api
    assert "top_scorelines: asArray(record.top_scorelines).map(normalizeScorelinePick)" in api
    assert "midband_scorelines: asArray(record.midband_scorelines)" in api
    assert "high_total: Object.keys(highTotal).length" in api
    assert "very_high_total: Object.keys(veryHighTotal).length" in api
    assert "ah_key_scorelines: asArray(record.ah_key_scorelines)" in api


def test_dashboard_defaults_to_formal_first_upcoming_view() -> None:
    page = (ROOT / "apps/web/src/components/DashboardPage.tsx").read_text()

    assert 'useState<DashboardMode>("next36")' in page
    assert "sortFormalFirst(view.upcoming)" in page
    assert "其他比赛分析参考" in page
