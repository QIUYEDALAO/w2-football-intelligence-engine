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
    assert 'AH_MAINLINE_AMBIGUOUS: "全场让球主盘口不明确"' in card
    assert 'AH_PRIMARY_MAINLINE_MISSING: "缺少可确认的全场让球主盘口"' in card
    assert (
        'AH_MAINLINE_JUMP_REQUIRES_PRIMARY_CONFIRMATION: "全场让球主盘口跳线缺少确认"'
        in card
    )
    assert "未出正式推荐原因" in card
    assert "模拟中位比分参考，不是推荐比分" in card
    assert "模拟中位比分参考未就绪" in card
    assert "scorelineHeroText" not in card
    assert "scoreText(match)" not in card
    assert "scoreline_picks" not in card
    assert "比分模拟参考" not in card
    assert "模拟比分参考：" not in card
    assert "最可能比分" not in card
    assert "最可能：" not in card
    assert "总进球≥" not in card
    assert "让球结算关键比分" not in card
    assert "全赢" not in card
    assert "半输" not in card
    assert "全输" not in card
    assert "高概率" not in card
    assert "中概率" not in card
    assert "低概率" not in card
    assert "推荐比分" not in card.replace("不是推荐比分", "")


def test_formal_card_copy_surfaces_locked_prematch_recommendations() -> None:
    card = (ROOT / "apps/web/src/components/RecommendationCard.tsx").read_text()
    types = (ROOT / "apps/web/src/types/dashboard.ts").read_text()

    assert "赛前锁定推荐" in card
    assert "赛前无正式推荐" in card
    assert "不随开赛后盘口或赛果重算" in card
    assert "不能在开赛后补造推荐" in card
    assert "待结算" in card
    assert "已结算" in card
    assert "待赛果确认" in card
    assert "locked_pre_match_recommendation" in types


def test_dashboard_defaults_to_formal_first_upcoming_view() -> None:
    page = (ROOT / "apps/web/src/components/DashboardPage.tsx").read_text()

    assert 'useState<DashboardMode>("next36")' in page
    assert "footballDayShanghai()" in page
    assert "sortFormalFirst(view.upcoming)" in page
    assert "其他比赛分析参考" in page


def test_completed_recap_empty_state_hides_diagnostics_by_default() -> None:
    page = (ROOT / "apps/web/src/components/DashboardPage.tsx").read_text()

    assert "本足球日暂无完场比赛" in page
    assert "北京时间中午 12:00 到次日 11:59" in page
    assert "shouldShowDiagnostics" in page
    assert 'params.get("debug") === "1"' in page
    assert 'params.get("diagnostics") === "1"' in page
    assert 'state === "empty" && view ? <DataDiagnosticsPanel' not in page
