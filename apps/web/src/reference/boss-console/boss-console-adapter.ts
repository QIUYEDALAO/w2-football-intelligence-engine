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
  BossRiskAxis,
} from "./boss-console-model";

function axis(
  level: BossRiskAxis["level"],
  label: string,
  code: string | null = null,
): BossRiskAxis {
  return { level, label, code };
}

function eventRisk(fixture: DashboardV2FixtureModel): BossRiskAxis {
  const code = fixture.reasonCode || "";
  if (code === "EVENT_RISK_HIGH") return axis("high", "高", code);
  if (code === "EVENT_RISK_MEDIUM") return axis("attention", "中", code);
  if (code === "EVENT_RISK_LOW") return axis("none", "低", code);
  return axis("unknown", "未评估", null);
}

function dataIntegrityRisk(fixture: DashboardV2FixtureModel): BossRiskAxis {
  const code = fixture.reasonCode || "";
  const reason = fixture.reasonLabel || code;
  const blockers: string[] = [];
  if (/(?:SCHEMA|CONFLICT)/.test(code)) blockers.push(`Schema/数据冲突：${reason}`);
  if (/(?:TEAM.*(?:MAPP|IDENTITY)|(?:MAPP|IDENTITY).*TEAM)/.test(code)) {
    blockers.push(`球队映射缺失：${reason}`);
  }
  if (
    /(?:ODDS|MARKET|QUOTE)/.test(code)
    || ["PROVIDER_EMPTY", "MARKET_UNAVAILABLE"].includes(fixture.oddsCollectionStatus || "")
  ) {
    blockers.push(`赔率缺失：${reason}`);
  }
  const xg = fixture.dataFacts.find((fact) => fact.startsWith("真实 xG") && !fact.includes("已就绪"));
  if (/(?:^|_)XG(?:_|$)/.test(code) || xg) {
    blockers.push(`xG 缺失：${xg?.replace(/^真实 xG\s*/, "") || reason}`);
  }
  const marketIdentity = fixture.dataFacts.find(
    (fact) => fact.startsWith("盘口身份") && !fact.includes("完整"),
  );
  if (marketIdentity) blockers.push(marketIdentity);
  if (blockers.length) {
    return axis("high", blockers.join("；"), code || fixture.oddsCollectionStatus || null);
  }
  if (/(?:DYNAMIC|CALIBRATION|LINEUP)/.test(code)) {
    return axis("none", "数据身份与证据无独立阻断", null);
  }
  if (fixture.dataStatus === "BLOCKED") {
    return axis("high", reason || "数据证据阻断", code || null);
  }
  if (fixture.dataStatus === "STALE") return axis("attention", "赔率快照已过期", code || null);
  if (fixture.dataStatus === "PARTIAL") return axis("attention", reason || "数据证据不完整", code || null);
  return axis("none", "数据身份与证据完整", null);
}

function modelUncertainty(fixture: DashboardV2FixtureModel): BossRiskAxis {
  const code = fixture.reasonCode || "";
  const uncertainty = fixture.quote?.uncertainty;
  const blockers: string[] = [];
  const warnings: string[] = [];
  if (/(?:DYNAMIC.*(?:MISSING|UNAVAILABLE|NOT_READY))/.test(code)) {
    blockers.push("dynamic evaluation 缺失");
  } else if (!fixture.dynamicSnapshot) {
    warnings.push("dynamic evaluation 尚未投影");
  }
  if (
    /CALIBRATION/.test(code)
    || /(?:尚未|待确认|BASELINE|UNVERIFIED)/i.test(fixture.calibrationLabel)
  ) {
    warnings.push(`calibration 未验证：${fixture.calibrationLabel}`);
  }
  if (uncertainty == null) {
    warnings.push("模型不确定性尚未量化");
  }
  if (blockers.length) return axis("high", [...blockers, ...warnings].join("；"), code || null);
  if (warnings.length) return axis("attention", warnings.join("；"), code || null);
  if (uncertainty == null) return axis("attention", "模型不确定性尚未量化", code || null);
  return axis("none", `EV 标准误 ±${(uncertainty * 100).toFixed(1)}%`, null);
}

function collectionRuntimeRisk(
  fixture: DashboardV2FixtureModel,
  automaticCollectionPaused: boolean,
): BossRiskAxis {
  const code = fixture.reasonCode || "";
  const reason = fixture.reasonLabel || code;
  if (fixture.decisionOutcome === "SYSTEM_DEGRADED") {
    return axis("high", `系统降级：${reason || "SYSTEM_DEGRADED"}`, code || "SYSTEM_DEGRADED");
  }
  if (/(?:SCHEMA|CONFLICT)/.test(code)) return axis("high", `Schema/数据冲突：${reason}`, code);
  if (/QUOTA/.test(code)) return axis("high", `Provider 配额异常：${reason}`, code);
  if (/(?:FAILED|ERROR)/.test(code)) return axis("high", `采集运行失败：${reason}`, code);
  if (automaticCollectionPaused) return axis("attention", "调度暂停（受控状态）", null);
  if (fixture.oddsCollectionStatus === "WAITING_WINDOW") {
    return axis("none", "等待合法采集窗口", null);
  }
  if (fixture.oddsCollectionStatus === "WINDOW_DUE") {
    return axis("attention", "采集窗口已到，等待任务", null);
  }
  if (["PROVIDER_EMPTY", "MARKET_UNAVAILABLE"].includes(fixture.oddsCollectionStatus || "")) {
    return axis("none", "Provider 请求已完成，本轮无可用赔率", null);
  }
  return axis("none", "采集运行正常", null);
}

function decisionStatus(fixture: DashboardV2FixtureModel): BossDecisionItem["status"] {
  if (fixture.decisionTier === "ANALYSIS_PICK") return "pick";
  if (fixture.decisionTier === "NOT_READY") return "not-ready";
  return "watch";
}

function priorityLabel(index: number): string {
  return `A${index + 1}`;
}

function nextAction(
  fixture: DashboardV2FixtureModel,
  automaticCollectionPaused: boolean,
): [string, string] {
  if (fixture.nextEvaluationAt) return ["下次评估", "新盘口 / 首发 / 阵容异常"];
  if (automaticCollectionPaused) return ["计划复核：赛前30分钟", "状态：受控采集尚未安排"];
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

function noEdgeCopy(fixture: DashboardV2FixtureModel): string {
  if (fixture.dataStatus === "STALE") {
    return "旧报价仅供参考，等待下一次受控采集";
  }
  const cashflowEdge = fixture.quote?.cashflowPriceEdge;
  if (cashflowEdge != null && cashflowEdge < 0.05) {
    return `五态现金流价格优势 ${(cashflowEdge * 100).toFixed(1)}%，低于 5.0% 门槛`;
  }
  const ev = fixture.quote?.expectedValue;
  const evMinusSe = fixture.dynamicSnapshot?.currentEvMinusSe;
  if (ev != null && evMinusSe != null && evMinusSe <= 0) {
    return `EV ${ev >= 0 ? "+" : ""}${(ev * 100).toFixed(1)}%，但 EV-SE = ${(evMinusSe * 100).toFixed(1)}%，稳健性未通过`;
  }
  return "当前完整快照未通过 EV、五态现金流价格优势与 EV-SE 稳健门";
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
  if ((fixture.quote?.expectedValue ?? 0) >= 0.15) {
    risks.push("EV_PLAUSIBILITY_REVIEW：异常高 EV 需单独复核");
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
  const decisions = model.fixtures.map((fixture, index) => {
    const status = decisionStatus(fixture);
    const [action, detail] = nextAction(fixture, model.health.automaticCollectionPaused);
    const quote = fixture.quote;
    const dynamic = fixture.dynamicSnapshot;
    const mainlinePrices = quote?.marketMainlineOverPrice != null
      ? `大${quote.marketMainlineOverPrice.toFixed(2)} / 小${quote.marketMainlineUnderPrice?.toFixed(2) ?? "--"}`
      : quote?.marketMainlineHomePrice != null
        ? `主${quote.marketMainlineHomePrice.toFixed(2)} / 客${quote.marketMainlineAwayPrice?.toFixed(2) ?? "--"}`
        : "双边中位价待确认";
    return {
      id: fixture.fixtureId,
      priority: priorityLabel(index),
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
            ? noEdgeCopy(fixture)
            : fixture.reasonLabel || "尚未进入完整评估窗口",
      modelProbability: fixture.quote?.modelProbability ?? null,
      marketProbability: fixture.quote?.marketProbability ?? null,
      probabilityDelta: fixture.quote?.probabilityDelta ?? null,
      expectedValue: fixture.quote?.expectedValue ?? null,
      uncertainty: fixture.quote?.uncertainty ?? null,
      scorelineProjection: fixture.scorelineProjection,
      candidateRole: quote?.candidateRole ?? null,
      marketPolicyLabel: quote?.marketPolicyLabel ?? null,
      marketMainlineLabel: quote
        ? `市场主线：${quote.marketMainlineLine} · ${quote.marketMainlineBookmakerCount}家完整双边 · ${quote.marketMainlineVoteCount}票 · ${mainlinePrices}`
        : null,
      executionQuoteLabel: quote
        ? `分析选择：${fixture.primaryMarketLabel} · ${quote.candidateRole === "ALTERNATE_LINE" ? "替代盘" : "市场主线"} · ${quote.bookmaker}`
        : null,
      marketLadder: quote?.ladder ?? [],
      eventRisk: eventRisk(fixture),
      dataIntegrityRisk: dataIntegrityRisk(fixture),
      modelUncertainty: modelUncertainty(fixture),
      collectionRuntimeRisk: collectionRuntimeRisk(
        fixture,
        model.health.automaticCollectionPaused,
      ),
      lineupPending: fixture.dataFacts.some(
        (fact) => fact.includes("首发") && !fact.includes("已就绪"),
      ),
      nextAction: action,
      nextDetail: detail,
      snapshotAt: fixture.quote?.capturedAt ?? null,
      lifecycleState: dynamic?.state ?? null,
      quoteAgeSeconds: dynamic?.quoteAgeSeconds ?? null,
      latestCheckpoint: dynamic?.checkpoint ?? null,
      nextCheckpoint: dynamic?.nextCheckpoint ?? null,
      automaticRefreshStatus: dynamic?.automaticRefreshStatus ?? "等待评估快照",
      lineupFacts: fixture.lineupFacts,
      ledgerCode: fixture.tracking.captureHash || "—",
      ledgerStatus: fixture.tracking.label,
      ledgerDetail: fixture.tracking.detail,
      reasons: decisionReasons(fixture),
      risks: decisionRisks(fixture),
      marketIdentityRisk:
        quote?.candidateRole === "ALTERNATE_LINE" ? "替代盘，禁止冒充主线" : "主线身份完整",
      lineupRisk: fixture.dataFacts.some(
        (fact) => fact.includes("首发") && !fact.includes("已就绪"),
      ) ? "首发待确认" : "首发证据已就绪",
    } satisfies BossDecisionItem;
  });

  return {
    release: model.release,
    ledger: model.ledger,
    decisions,
    selectedDecisionId: model.selectedFixtureId,
    leaguePerformance: dedupeLeaguePerformance(model.leaguePerformance),
    automaticCollectionPaused: model.health.automaticCollectionPaused,
    eventRiskExceptionCount: new Set(
      decisions.filter((item) => item.eventRisk.level === "high").map((item) => item.id),
    ).size,
    operationalRiskExceptionCount: new Set(
      decisions
        .filter((item) => (
          item.dataIntegrityRisk.level === "high"
          || item.collectionRuntimeRisk.level === "high"
        ))
        .map((item) => item.id),
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
      candidateStatus: "OFF",
      formalStatus: "OFF",
      lockStatus: "OFF",
      productionStatus: "OFF",
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
