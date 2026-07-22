import type {
  DashboardDayView,
  DashboardMatchCard,
  DashboardPerformance,
  ReleaseSyncState,
} from "../../types/dashboard";
import {
  adaptDashboardV2,
} from "../dashboard-v2/dashboard-v2-adapter";
import type {
  DashboardV2FixtureModel,
  DashboardV2LeaguePerformanceRow,
  DashboardV2ViewModel,
} from "../dashboard-v2/dashboard-v2-model";
import type {
  BossConsoleModel,
  BossDecisionItem,
  BossRiskLevel,
} from "./boss-console-model";

function riskLevel(fixture: DashboardV2FixtureModel): BossRiskLevel {
  if (fixture.dataStatus === "BLOCKED" || fixture.decisionTier === "NOT_READY") return "high";
  const uncertainty = fixture.quote?.uncertainty;
  if (uncertainty != null && uncertainty >= 0.05) return "high";
  if (uncertainty != null && uncertainty < 0.04) return "low";
  return "medium";
}

function riskCopy(level: BossRiskLevel): string {
  return level === "high" ? "高" : level === "low" ? "低" : "中";
}

function decisionStatus(fixture: DashboardV2FixtureModel): BossDecisionItem["status"] {
  if (fixture.decisionTier === "ANALYSIS_PICK") return "pick";
  if (fixture.decisionTier === "NOT_READY") return "not-ready";
  return "watch";
}

function priorityLabel(status: BossDecisionItem["status"], index: number): string {
  const prefix = status === "pick" ? "P" : status === "watch" ? "W" : "N";
  return `${prefix}${index + 1}`;
}

function nextAction(fixture: DashboardV2FixtureModel): [string, string] {
  if (fixture.nextEvaluationAt) return ["下次评估", "新盘口 / 首发 / 阵容异常"];
  if (fixture.decisionTier === "NOT_READY") return ["待安排", "受控采集窗口"];
  if (fixture.decisionTier === "ANALYSIS_PICK") return ["赛前30分钟", "新盘口 / 首发 / 阵容异常"];
  return ["等待新盘口", "下一次受控采集"];
}

function decisionReasons(fixture: DashboardV2FixtureModel): string[] {
  const reasons = fixture.dataFacts.filter(Boolean).slice(0, 3);
  if (fixture.quote?.probabilityDelta != null) {
    reasons.unshift(`模型与同盘口市场概率差为 ${(fixture.quote.probabilityDelta * 100).toFixed(1)}pp`);
  }
  return reasons.slice(0, 3).length
    ? reasons.slice(0, 3)
    : ["当前证据不足以形成分析方向", "保持真实状态，不强行产生建议", "等待下一次受控评估"];
}

function decisionRisks(fixture: DashboardV2FixtureModel): string[] {
  const risks: string[] = [];
  if (fixture.calibrationLabel) risks.push(fixture.calibrationLabel);
  if (fixture.dataFacts.some((fact) => fact.includes("首发") && !fact.includes("已就绪"))) {
    risks.push("首发尚未公布，阵容变化可能影响结论");
  }
  if (fixture.quote?.uncertainty != null) {
    risks.push(`EV 标准误 ±${(fixture.quote.uncertainty * 100).toFixed(1)}%`);
  }
  if (fixture.decisionTier !== "ANALYSIS_PICK") risks.push("当前不进入验证推荐分母");
  return risks.slice(0, 3).length
    ? risks.slice(0, 3)
    : ["盘口或首发数据尚不完整", "不可使用旧快照替代执行报价", "保持 NOT_READY"];
}

function leagueFallbackKey(league: string): string {
  return league
    .toLowerCase()
    .replace(/allsvenskan|瑞典超/g, "allsvenskan")
    .replace(/eliteserien|挪威超/g, "eliteserien")
    .replace(/serie a|巴甲/g, "brasileirao_serie_a")
    .replace(/super league|中超/g, "chinese_super_league")
    .replace(/[^a-z0-9\u4e00-\u9fff]+/g, "_")
    .replace(/^_|_$/g, "");
}

export function dedupeLeaguePerformance(
  rows: DashboardV2LeaguePerformanceRow[],
): DashboardV2LeaguePerformanceRow[] {
  const canonical = new Map<string, DashboardV2LeaguePerformanceRow>();
  for (const row of rows) {
    if (row.eligibleCount <= 0) continue;
    const key = row.competitionKey || leagueFallbackKey(row.league);
    const current = canonical.get(key);
    if (
      !current
      || row.eligibleCount > current.eligibleCount
      || (
        row.eligibleCount === current.eligibleCount
        && row.clvSampleCount > current.clvSampleCount
      )
    ) {
      canonical.set(key, row);
    }
  }
  return [...canonical.values()];
}

export function adaptDashboardV2ToBossConsole(model: DashboardV2ViewModel): BossConsoleModel {
  const counters = { pick: 0, watch: 0, "not-ready": 0 };
  const decisions = model.fixtures.map((fixture) => {
    const status = decisionStatus(fixture);
    const index = counters[status]++;
    const risk = riskLevel(fixture);
    const [action, detail] = nextAction(fixture);
    return {
      id: fixture.fixtureId,
      priority: priorityLabel(status, index),
      kickoffUtc: fixture.kickoffUtc,
      fixtureStatus: fixture.status,
      league: fixture.competition,
      match: `${fixture.homeTeam} vs ${fixture.awayTeam}`,
      status,
      decision: status === "pick" ? "分析建议" : status === "watch" ? "继续观察" : "暂不可判断",
      recommendation:
        status === "pick"
          ? fixture.primaryMarketLabel.replace(/^让球 · |^大小球 · /, "")
          : status === "watch"
            ? "优势不足 · 暂不选方向"
            : fixture.reasonLabel || "尚未进入完整评估窗口",
      modelProbability: fixture.quote?.modelProbability ?? null,
      marketProbability: fixture.quote?.marketProbability ?? null,
      probabilityDelta: fixture.quote?.probabilityDelta ?? null,
      expectedValue: fixture.quote?.expectedValue ?? null,
      uncertainty: fixture.quote?.uncertainty ?? null,
      scorelineProjection: fixture.scorelineProjection,
      risk: riskCopy(risk),
      riskLevel: risk,
      riskNote:
        status === "not-ready"
          ? fixture.reasonLabel || "数据未齐"
          : risk === "high"
            ? "证据波动"
            : risk === "low"
              ? "盘口稳定"
              : "首发未确认",
      lineupPending: fixture.dataFacts.some(
        (fact) => fact.includes("首发") && !fact.includes("已就绪"),
      ),
      nextAction: action,
      nextDetail: detail,
      snapshotAt: fixture.quote?.capturedAt ?? null,
      ledgerCode: fixture.tracking.captureHash || "—",
      ledgerStatus: fixture.tracking.label,
      ledgerDetail: fixture.tracking.detail,
      reasons: decisionReasons(fixture),
      risks: decisionRisks(fixture),
    } satisfies BossDecisionItem;
  });

  return {
    release: model.release,
    ledger: model.ledger,
    decisions,
    selectedDecisionId: model.selectedFixtureId,
    leaguePerformance: dedupeLeaguePerformance(model.leaguePerformance),
    automaticCollectionPaused: model.health.automaticCollectionPaused,
    riskExceptionCount: new Set(
      decisions.filter((item) => item.riskLevel === "high").map((item) => item.id),
    ).size,
    lineupPendingCount: new Set(
      decisions.filter((item) => item.lineupPending).map((item) => item.id),
    ).size,
    lastCheckedAt: model.release.pageUpdatedAt,
    runtime: {
      schemaStatus: "PASS",
      serviceStatus: "HEALTHY",
      providerStatus: model.health.automaticCollectionPaused ? "DISABLED" : "ENABLED",
      schedulerStatus: model.health.automaticCollectionPaused ? "STOPPED" : "RUNNING",
      formalStatus: "DISABLED",
      lockProductionStatus: "DISABLED",
    },
  };
}

export function adaptBossDecisionConsole(
  dayView: DashboardDayView,
  _legacyMatches: DashboardMatchCard[],
  performance?: DashboardPerformance,
  release?: ReleaseSyncState,
): BossConsoleModel {
  return adaptDashboardV2ToBossConsole(adaptDashboardV2(dayView, performance, release));
}
