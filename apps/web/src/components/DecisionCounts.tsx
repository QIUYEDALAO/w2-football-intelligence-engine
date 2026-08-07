import type {
  DashboardDayView,
  DashboardDayViewCard,
  DashboardPerformance,
} from "../types/dashboard";

/** Legacy adapter hook; public attention now follows intelligence state, never V4. */
export function isReadyRecommendation(card: DashboardDayViewCard): boolean {
  if (!card.intelligence_state) {
    return ["RECOMMEND", "ANALYSIS_PICK"].includes(card.decision_tier)
      && card.data_status === "READY";
  }
  return ["MARKET_ANOMALY", "MODEL_MARKET_DISAGREEMENT", "MARKET_MOVEMENT"].includes(
    card.intelligence_state,
  );
}

export function percent(value?: number | null): string {
  if (value == null || !Number.isFinite(value)) return "样本不足";
  return `${Math.round(value * 100)}%`;
}

export function DecisionCounts({
  dayView,
  performance,
}: {
  dayView: DashboardDayView;
  performance?: DashboardPerformance;
}) {
  const intelligenceMetrics = [
    ["监测比赛", dayView.counts.monitored_fixtures, "monitored fixtures"],
    ["市场完整", dayView.counts.market_complete_fixtures, "market-complete fixtures"],
    ["新鲜报价", dayView.counts.fresh_quotes, "fresh quotes"],
    ["市场稳定", dayView.counts.market_stable_fixtures, "market-stable fixtures"],
    ["市场变化", dayView.counts.market_movement_fixtures, "market-movement fixtures"],
    ["模型诊断警告", dayView.counts.model_diagnostic_warnings, "model diagnostic warnings"],
    ["数据事件", dayView.counts.data_incidents, "data incidents"],
    ["采集事件", dayView.counts.collection_incidents, "collection incidents"],
  ] as const;
  const cohort = performance?.forward_ledger?.performance_cohort;
  const legacyMetrics = [
    ["未来比赛", dayView.counts.total, "当前赛前窗口"],
    ["身份未就绪", dayView.counts.identity_not_ready, "canonical fixture/team identity"],
    ["xG 未就绪", dayView.counts.xg_not_ready, "真实历史 xG 不足"],
    ["模型 READY", dayView.counts.model_ready, "xG 基线模拟已生成"],
    ["等待新鲜赔率", dayView.counts.waiting_fresh_quote, "旧盘只作参考"],
    ["当前可执行赔率", dayView.counts.executable_quote, "身份和新鲜度完整"],
    ["NO_EDGE", dayView.counts.no_edge, "三项优势门未全部通过"],
    ["分析建议", dayView.cards.filter(isReadyRecommendation).length, "分析级证据完整后才置顶"],
    ["阵容待确认", dayView.counts.lineup_pending, "远离开球仅作 advisory"],
    ["ratings 增强缺失", dayView.counts.ratings_enhancement_missing, "不阻断 xG 基线"],
    ["team value 增强缺失", dayView.counts.team_value_enhancement_missing, "不使用代理值"],
    ["纳入统计", cohort?.eligible_count ?? 0, `有效输赢命中率 ${percent(cohort?.outcomes.hit_rate)}`],
    ["今日待评估", dayView.counts.not_ready + dayView.counts.watch + dayView.counts.skip, "按开球时间继续观察"],
    [dayView.environment === "production" ? "正式可锁" : "可锁审批", dayView.counts.lock_eligible, "Candidate / Formal / Lock / Production 均关闭"],
  ] as const;
  const metrics = dayView.counts.monitored_fixtures == null
    ? legacyMetrics
    : intelligenceMetrics;
  return (
    <section className="decision-counts" aria-label="Market Overview">
      {metrics.map(([label, value, hint]) => (
        <div className="decision-count" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
          <small>{hint}</small>
        </div>
      ))}
    </section>
  );
}
