import { asRecord, textValue } from "../lib/normalize";
import type {
  DashboardDayView,
  DashboardDayViewCard,
  DashboardPerformance,
} from "../types/dashboard";

const MARKET_ANCHOR_DISPLAY_ENABLED =
  import.meta.env?.VITE_W2_MARKET_ANCHOR_DISPLAY_ENABLED === "true";
const MARKET_ANCHOR_MIN_DIVERGENCE = Number(
  import.meta.env?.VITE_W2_MARKET_ANCHOR_MIN_DIVERGENCE ?? 0.05,
);

export function isReadyRecommendation(card: DashboardDayViewCard): boolean {
  const pickTier = ["RECOMMEND", "ANALYSIS_PICK"].includes(card.decision_tier);
  if (!pickTier || card.data_status !== "READY") return false;
  if (!MARKET_ANCHOR_DISPLAY_ENABLED || card.decision_tier === "RECOMMEND")
    return true;
  const divergence = asRecord(card.model_market_divergence);
  const status = textValue(divergence.status, "UNKNOWN").toUpperCase();
  const directionAllowed =
    divergence.direction_allowed === true ||
    textValue(divergence.direction_allowed).toLowerCase() === "true";
  const magnitude =
    typeof divergence.magnitude === "number"
      ? Math.abs(divergence.magnitude)
      : null;
  return (
    card.probability_source === "MARKET_DEVIG" &&
    ["READY", "SIGNIFICANT", "ACTIONABLE"].includes(status) &&
    directionAllowed &&
    magnitude != null &&
    magnitude >= MARKET_ANCHOR_MIN_DIVERGENCE
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
  const lockLabel =
    dayView.environment === "production" ? "正式可锁" : "可锁审批";
  const readyRecommendations = dayView.cards.filter(
    isReadyRecommendation,
  ).length;
  const cohort = performance?.forward_ledger?.performance_cohort;
  const metrics = [
    ["未来比赛", dayView.counts.total, "当前赛前窗口"],
    ["身份未就绪", dayView.counts.identity_not_ready, "canonical fixture/team identity"],
    ["xG 未就绪", dayView.counts.xg_not_ready, "真实历史 xG 不足"],
    ["模型 READY", dayView.counts.model_ready, "xG 基线模拟已生成"],
    ["等待新鲜赔率", dayView.counts.waiting_fresh_quote, "旧盘只作参考"],
    ["当前可执行赔率", dayView.counts.executable_quote, "身份和新鲜度完整"],
    ["NO_EDGE", dayView.counts.no_edge, "三项优势门未全部通过"],
    ["分析建议", readyRecommendations, "分析级证据完整后才置顶"],
    ["阵容待确认", dayView.counts.lineup_pending, "远离开球仅作 advisory"],
    ["ratings 增强缺失", dayView.counts.ratings_enhancement_missing, "不阻断 xG 基线"],
    ["team value 增强缺失", dayView.counts.team_value_enhancement_missing, "不使用代理值"],
    [
      "纳入统计",
      cohort?.eligible_count ?? 0,
      `有效输赢命中率 ${percent(cohort?.outcomes.hit_rate)}`,
    ],
    [
      "今日待评估",
      dayView.counts.not_ready + dayView.counts.watch + dayView.counts.skip,
      "按开球时间继续观察",
    ],
    [lockLabel, dayView.counts.lock_eligible, "Candidate / Formal / Lock / Production 均关闭"],
  ] as const;
  return (
    <section className="decision-counts" aria-label="今日决策计数">
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
