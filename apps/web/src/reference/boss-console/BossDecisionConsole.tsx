import type {
  DashboardDayView,
  DashboardMatchCard,
  DashboardPerformance,
  ReleaseSyncState,
} from "../../types/dashboard";
import { adaptBossDecisionConsole } from "./boss-console-adapter";
import type { BossConsoleModel } from "./boss-console-model";
import { BossDecisionConsoleReference } from "./BossDecisionConsoleReference";

export interface BossDecisionConsoleProps {
  dayView: DashboardDayView;
  legacyMatches: DashboardMatchCard[];
  performance?: DashboardPerformance;
  release?: ReleaseSyncState;
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : value == null ? "" : String(value);
}

function price(value: unknown): string {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toFixed(2) : "--";
}

export function applyProductionDashboardTruth(
  model: BossConsoleModel,
  dayView: DashboardDayView,
): BossConsoleModel {
  const cards = new Map(dayView.cards.map((card) => [card.fixture_id, card]));
  const decisions = model.decisions.map((decision) => {
    const card = cards.get(decision.id);
    const reference = record(card?.last_known_odds);
    const markets = record(reference.markets);
    const ah = record(markets.ah);
    const ou = record(markets.ou);
    const market = Object.keys(ah).length ? ah : ou;
    const referenceOnly = text(reference.status) === "REFERENCE_ONLY"
      && reference.executable === false
      && Object.keys(market).length > 0;
    const notReady = decision.status === "not-ready"
      || decision.dataIntegrityRisk.level === "high";
    const dynamicGateProjectionMissing = decision.lifecycleState === "NO_EDGE_CURRENT"
      && [
        decision.modelProbability,
        decision.marketProbability,
        decision.probabilityDelta,
        decision.expectedValue,
        decision.uncertainty,
      ].some((value) => value == null);
    if (!referenceOnly && !notReady && !dynamicGateProjectionMissing) return decision;
    const isAh = market === ah;
    const line = text(market.line || market.home_line || market.over_line);
    const prices = isAh
      ? `主${price(market.home_price)} / 客${price(market.away_price)}`
      : `大${price(market.over_price)} / 小${price(market.under_price)}`;
    const bookmakers = Array.isArray(reference.bookmakers)
      ? reference.bookmakers.map(text).filter(Boolean)
      : [];
    const bookmaker = text(market.bookmaker_name) || bookmakers[0] || "已审计报价";
    const capturedAt = text(market.captured_at || reference.captured_at) || "UNKNOWN";
    const freshness = text(market.freshness_status) || "UNKNOWN";
    const decisionV4 = record(card?.recommendation_decision_v4);
    const modelDecisionNotReady = referenceOnly
      && decision.modelProbability == null
      && text(decisionV4.outcome) !== "NO_EDGE";
    return {
      ...decision,
      ...(modelDecisionNotReady ? {
        recommendation: "真实参考赔率已就绪，模型决策未就绪",
      } : dynamicGateProjectionMissing ? {
        recommendation: "动态评估已记录；完整模型与市场概率未投影，暂不展示稳健门结论",
      } : {}),
      ...(dynamicGateProjectionMissing ? {
        modelUncertainty: {
          level: "attention" as const,
          label: "dynamic evaluation 投影不完整",
          code: "DYNAMIC_EVALUATION_PROJECTION_MISSING",
        },
      } : {}),
      ...(referenceOnly ? {
        marketPolicyLabel: "REFERENCE_ONLY · 不可执行",
        marketMainlineLabel: `真实参考盘口（不可执行）：${line} · ${prices}`,
        executionQuoteLabel: `来源：${bookmaker} · 采集时间 ${capturedAt} · 新鲜度 ${freshness}`,
        marketIdentityRisk: "参考报价完整，禁止执行",
      } : {}),
    };
  });
  return {
    ...model,
    decisions,
  };
}

export function BossDecisionConsole(props: BossDecisionConsoleProps) {
  const model = adaptBossDecisionConsole(
    props.dayView,
    props.legacyMatches,
    props.performance,
    props.release,
  );
  const truthfulModel = applyProductionDashboardTruth(model, props.dayView);
  return (
    <>
      {truthfulModel.ledger.available === false ? (
        <section data-ui="forward-ledger-unavailable" aria-label="前向验证账本不可用">
          <strong>前向验证统一账本</strong>
          <p>账本 checkpoint 投影不可用；未用 0 代替缺失数据。</p>
        </section>
      ) : null}
      <BossDecisionConsoleReference model={truthfulModel} />
    </>
  );
}
