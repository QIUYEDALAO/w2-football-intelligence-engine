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
    upcoming = (ROOT / "apps/web/src/components/UpcomingFixtureCard.tsx").read_text()

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
    assert "formalBlockerLabel" in card
    assert 'W2_FORMAL_RECOMMENDATION_ENABLED: "正式推荐开关未开启"' in card
    assert "formalSuppressedReasonLabel" in card
    assert 'reason.split("=")' in card
    assert "未达到正式推荐条件" in card
    assert "全场让球主盘口不明确" in card
    assert "盘口未采集" in card
    assert "盘口未返回" in card
    assert "blockerLabel(blocker)" in upcoming
    assert "数据状态待确认" in upcoming
    assert 'source === "formal_simulation"' in card
    assert "未出正式推荐原因" in card
    assert "模拟比分参考，不是推荐比分" in card
    assert "最可能：" in card
    assert "总进球≥" in card
    assert "让球结算关键比分" in card
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


def test_dashboard_defaults_to_boss_decision_view() -> None:
    page = (ROOT / "apps/web/src/components/DashboardPage.tsx").read_text()
    boss_view = (ROOT / "apps/web/src/components/BossDecisionView.tsx").read_text()
    formatters = (ROOT / "apps/web/src/lib/formatters.ts").read_text()

    assert 'const mode: DashboardMode = "future"' in page
    assert "未来 36 小时暂无比赛" in page
    assert "未来 14 天暂无可展示比赛" in page
    assert "BossDecisionView" in page
    assert "footballDayShanghai()" in page
    assert "footballDayShanghai" in formatters
    assert "next_available_date" in page
    assert "selected_date_has_data" in page
    assert "rawHour === 24 ? 0 : rawHour" in formatters
    assert "sortFormalFirst" not in page
    assert "DecisionCounts" in boss_view
    assert "EvidencePanel" in boss_view
    assert "readyRecommendations" in boss_view
    assert "todaySchedule" in boss_view
    assert "futureSchedule" in boss_view
    assert "ScheduleSection" in boss_view
    assert "CoverageFoldout" in boss_view
    assert "已形成建议" in boss_view
    assert "赛中 / 刚开赛" in boss_view
    assert "marketSourceLabel" in boss_view
    assert "VerificationPreview" in boss_view
    assert "LeaguePerformancePreview" in boss_view
    assert "DecisionRow" in boss_view
    assert "pickSelectionLabel" in boss_view
    assert 'value === "HOME_AH"' in boss_view
    assert 'value === "AWAY_AH"' in boss_view
    assert "displayLineForTeam" in boss_view
    assert "世界杯输出按 staging 保守展示" in boss_view
    assert "L2 技术诊断" in boss_view
    assert "近 30 天" not in boss_view
    assert "最多 3 场" not in boss_view
    assert (
        "orderedForTriage(dayView.cards.filter(isReadyRecommendation)).slice(0, 3)"
        not in boss_view
    )
    assert (
        "orderedForTriage(activeCards.filter(isReadyRecommendation)).slice(0, 3)"
        not in boss_view
    )
    assert "performance_cohort" in boss_view
    assert "outcomes_canonical" not in boss_view
    assert "验证推荐与赛果" in boss_view
    assert "全部已处理" not in boss_view
    assert "可核验 {settled}/{processed}" not in boss_view
    assert "页面更新" in boss_view
    assert "全局赔率确认" in boss_view
    assert "下次采集" in boss_view
    assert "最近盘口" in boss_view
    assert "已过期，仅参考" in boss_view
    assert "已有早盘·待临场更新" in boss_view
    assert "只读决策台" in boss_view
    assert "Boss View</button>" not in boss_view
    assert "T{minutesUntil" not in boss_view
    assert "本场尚未产生验证推荐" in boss_view
    assert "只有赛前形成分析参考或正式推荐" in boss_view
    assert "最后刷新" not in boss_view


def test_ah_display_helpers_use_home_team_view_contract() -> None:
    pricing_display = (ROOT / "apps/web/src/lib/pricingDisplay.ts").read_text()
    types = (ROOT / "apps/web/src/types/dashboard.ts").read_text()

    assert "ahDisplayContract" in pricing_display
    assert 'display_line_cn: Math.abs(numeric) < 0.005 ? "平手 0" : mainLine' in pricing_display
    assert 'numeric < 0 ? `主队 -${abs}` : `客队 -${abs}`' in pricing_display
    assert "home: `主队 ${formatSignedLine(numeric)}`" in pricing_display
    assert "away: `客队 ${formatSignedLine(-numeric)}`" in pricing_display
    assert "display_line_cn?: string | null" in types
    assert "home_display_line_cn?: string | null" in types
    assert "away_display_line_cn?: string | null" in types


def test_completed_recap_empty_state_hides_diagnostics_by_default() -> None:
    page = (ROOT / "apps/web/src/components/DashboardPage.tsx").read_text()

    assert "本足球日暂无完场比赛" in page
    assert "北京时间中午 12:00 到次日 11:59" in page
    assert "shouldShowDiagnostics" in page
    assert 'params.get("debug") === "1"' in page
    assert 'params.get("diagnostics") === "1"' in page
    assert 'state === "empty" && view ? <DataDiagnosticsPanel' not in page
