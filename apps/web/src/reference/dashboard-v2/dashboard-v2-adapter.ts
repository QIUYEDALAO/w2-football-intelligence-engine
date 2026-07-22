import type {
  DashboardDayView,
  DashboardDayViewCard,
  DashboardPerformance,
  ReleaseSyncState,
} from "../../types/dashboard";
import { translateCompetition, translateTeam } from "../../lib/formatters";
import type {
  DashboardV2DecisionTier,
  DashboardV2FixtureModel,
  DashboardV2LeaguePerformanceRow,
  DashboardV2ScorelineProjection,
  DashboardV2TrackingModel,
  DashboardV2ViewModel,
} from "./dashboard-v2-model";

type UnknownRecord = Record<string, unknown>;

function record(value: unknown): UnknownRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as UnknownRecord)
    : {};
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : value == null ? "" : String(value);
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function selectedCandidate(card: DashboardDayViewCard): UnknownRecord {
  return record(card.recommendation_decision_v3?.selected_candidate);
}

function evaluatedCandidate(card: DashboardDayViewCard): UnknownRecord {
  return record(record(card.recommendation_decision_v3).evaluated_candidate);
}

function selectedAnalysisEvidence(card: DashboardDayViewCard): UnknownRecord {
  const decision = record(card.recommendation_decision_v3);
  const evaluated = record(decision.evaluated_candidate);
  const evaluatedEvidence = record(evaluated.analysis_evidence);
  if (Object.keys(evaluatedEvidence).length) return evaluatedEvidence;
  const candidate = selectedCandidate(card);
  const nested = record(candidate.analysis_evidence);
  return Object.keys(nested).length ? nested : candidate;
}

function selectedQuoteIdentity(card: DashboardDayViewCard): UnknownRecord {
  const evidenceIdentity = record(selectedAnalysisEvidence(card).quote_identity);
  return Object.keys(evidenceIdentity).length
    ? evidenceIdentity
    : record(selectedCandidate(card).quote_identity);
}

function selectedQuote(card: DashboardDayViewCard): UnknownRecord {
  const candidate = selectedCandidate(card);
  const selection = text(candidate.selection).toLowerCase().replace("_ah", "");
  return record(record(selectedQuoteIdentity(card).quotes)[selection]);
}

function fieldReadiness(card: DashboardDayViewCard, field: string): UnknownRecord {
  const statuses = record(card.data_readiness).field_statuses;
  if (!Array.isArray(statuses)) return {};
  return record(statuses.find((item) => text(record(item).field) === field));
}

function nextCheckpoint(checkpoint: string): string | null {
  const sequence = ["opening", "T-24h", "T-12h", "T-6h", "T-3h", "T-1h", "LINEUP_CONFIRMED", "T-30m_VALIDATION_LOCK"];
  const index = sequence.indexOf(checkpoint);
  return index >= 0 && index < sequence.length - 1 ? sequence[index + 1] : null;
}

function dynamicSnapshot(card: DashboardDayViewCard): DashboardV2FixtureModel["dynamicSnapshot"] {
  const lifecycle = record(card.dynamic_prematch);
  const current = Array.isArray(lifecycle.current) ? lifecycle.current.map(record) : [];
  const selected = current[0];
  if (!selected) return null;
  const evaluatedAt = text(selected.evaluated_at) || null;
  const capturedAt = text(selected.capture_at) || null;
  const evaluated = evaluatedAt ? new Date(evaluatedAt).getTime() : Number.NaN;
  const captured = capturedAt ? new Date(capturedAt).getTime() : Number.NaN;
  const checkpoint = text(selected.checkpoint) || null;
  const state = text(selected.state);
  return {
    state,
    evaluatedAt,
    capturedAt,
    quoteAgeSeconds: Number.isFinite(evaluated) && Number.isFinite(captured)
      ? Math.max(0, Math.round((evaluated - captured) / 1000))
      : null,
    checkpoint,
    nextCheckpoint: checkpoint ? nextCheckpoint(checkpoint) : null,
    automaticRefreshStatus: state === "LINEUP_READY_MARKET_REFRESH_PENDING"
      ? "首发后盘口刷新中"
      : state === "STALE_PENDING_REFRESH"
        ? "等待自动刷新"
        : "已评估当前快照",
    currentEvMinusSe: numberValue(selected.current_ev_minus_se),
    requiredDelta: numberValue(selected.required_delta),
  };
}

function lineupFacts(card: DashboardDayViewCard): string[] {
  const lineup = record(card.lineup_provenance);
  const features = Array.isArray(lineup.lineup_change_features)
    ? lineup.lineup_change_features.map(record)
    : [];
  if (lineup.confirmed !== true) return ["尚未到公布窗口或确认首发尚未取得"];
  const facts = ["确认首发 11/11 · 双方已确认"];
  for (const feature of features.slice(0, 2)) {
    const continuity = numberValue(feature.starter_continuity);
    const missing = numberValue(feature.regular_starters_missing);
    if (continuity != null) facts.push(`首发连续性 ${(continuity * 100).toFixed(1)}% · 常规主力缺席 ${missing ?? 0}`);
    if (feature.formation_changed === true) facts.push("阵型相对常用结构已变化");
    const mapping = numberValue(feature.mapping_coverage);
    const valuation = numberValue(feature.valuation_coverage);
    if (mapping != null || valuation != null) facts.push(`映射覆盖 ${((mapping ?? 0) * 100).toFixed(1)}% · 估值覆盖 ${((valuation ?? 0) * 100).toFixed(1)}%`);
  }
  facts.push("模型影响：仅 advisory · 数值调整关闭");
  return facts.slice(0, 6);
}

function decisionTier(card: DashboardDayViewCard): DashboardV2DecisionTier {
  const outcome = text(card.recommendation_decision_v3?.outcome).toUpperCase();
  if (outcome === "ANALYSIS_PICK") return "ANALYSIS_PICK";
  if (outcome === "NO_EDGE") return "NO_EDGE";
  if (outcome === "NOT_READY" || outcome === "SYSTEM_DEGRADED") return "NOT_READY";
  if (card.decision_tier === "ANALYSIS_PICK" || card.decision_tier === "RECOMMEND") {
    return "ANALYSIS_PICK";
  }
  if (card.decision_tier === "NOT_READY") return "NOT_READY";
  if (card.decision_tier === "SKIP") return "SKIP";
  return "WATCH";
}

function selectionLabel(market: string, selection: string): string {
  const normalized = selection.toUpperCase();
  if (market === "ASIAN_HANDICAP") {
    return normalized.startsWith("HOME") ? "主队" : normalized.startsWith("AWAY") ? "客队" : "方向";
  }
  if (market === "TOTALS") {
    return normalized.startsWith("OVER") ? "大" : normalized.startsWith("UNDER") ? "小" : "方向";
  }
  return normalized || "方向";
}

function marketLabel(market: string): string {
  if (market === "ASIAN_HANDICAP") return "让球";
  if (market === "TOTALS") return "大小球";
  if (market === "ONE_X_TWO") return "胜平负";
  return market || "市场";
}

function primaryMarketLabel(card: DashboardDayViewCard): string {
  const candidate = selectedCandidate(card);
  const market = text(candidate.market || card.pick?.market);
  const selection = text(candidate.selection || card.pick?.selection);
  const quote = selectedQuote(card);
  const line = text(quote.line || candidate.line || card.pick?.line);
  const odds = numberValue(quote.decimal_odds ?? candidate.odds ?? card.pick?.odds);
  if (!market || !selection) return card.reason_code ?? "等待评估";
  return `${marketLabel(market)} · ${selectionLabel(market, selection)}${line ? ` ${line}` : ""}${odds != null ? ` @${odds.toFixed(2)}` : ""}`;
}

function secondaryMarketLabel(card: DashboardDayViewCard): string | null {
  const pick = card.secondary_picks?.[0];
  if (!pick) return null;
  const market = text(pick.market);
  const selection = text(pick.tendency || pick.lean);
  const line = text(pick.line);
  const odds = numberValue(pick.odds);
  return `${marketLabel(market)} · ${selectionLabel(market, selection)}${line ? ` ${line}` : ""}${odds != null ? ` @${odds.toFixed(2)}` : ""}`;
}

function scorelineProjection(card: DashboardDayViewCard): DashboardV2ScorelineProjection | null {
  const projection = card.scoreline_reference?.scoreline_projection;
  if (!projection) return null;
  const projectionRecord = record(projection);
  const top3 = (projection.top3 ?? []).map((row) => ({
    scoreline: row.scoreline,
    sampleCount: row.sample_count ?? 0,
    unconditionalProbability: row.unconditional_probability ?? row.probability ?? 0,
    conditionalProbability: row.conditional_probability ?? 0,
    primarySettlement: row.primary_settlement === "HALF_WIN" ? "HALF_WIN" as const : "WIN" as const,
  }));
  const candidate = selectedCandidate(card);
  const market = text(candidate.market || card.pick?.market);
  const selection = text(candidate.selection || card.pick?.selection);
  const line = text(candidate.line || card.pick?.line);
  const constraintLabel = (value: unknown): string | null => {
    const constraint = record(value);
    const constraintMarket = text(constraint.market);
    const constraintSelection = text(constraint.selection);
    const constraintLine = text(constraint.line);
    if (!constraintMarket || !constraintSelection) return null;
    return `${selectionLabel(constraintMarket, constraintSelection)} ${constraintLine}`.trim();
  };
  const primary = constraintLabel(projectionRecord.primary_constraint)
    ?? (market && selection ? `${selectionLabel(market, selection)} ${line}`.trim() : "当前分析盘口");
  const secondaryConstraints = Array.isArray(projectionRecord.secondary_constraints)
    ? projectionRecord.secondary_constraints.map(constraintLabel).filter((value): value is string => Boolean(value))
    : [];
  return {
    status: projection.status === "READY" ? "READY" : "NOT_READY",
    simulationsRequested: projection.simulations_requested ?? 0,
    simulationsCompleted: projection.simulations_completed ?? 0,
    consistentSampleCount: projection.consistent_sample_count ?? 0,
    consistencyLabel: `全部符合：${primary}${secondaryConstraints.length ? ` · 次推${secondaryConstraints.join(" · ")}` : ""}`,
    decisionHash: projection.decision_hash ?? card.recommendation_decision_v3?.decision_hash ?? "",
    evidenceHash: projection.evidence_hash ?? "",
    blocker: projection.reason ?? null,
    top3,
  };
}

function trackingModel(
  card: DashboardDayViewCard,
  performance?: DashboardPerformance,
): DashboardV2TrackingModel {
  const details = performance?.forward_ledger?.validation_pending_status?.details ?? [];
  const pending = details.find(
    (item) => item.fixture_id === card.fixture_id && item.recommendation_scope === "VALIDATION" && item.capture_identity_hash,
  );
  if (pending) {
    return {
      status: "CAPTURED_PENDING",
      label: "验证 ledger 已记录",
      detail: pending.category === "WAITING_FINISH" ? "待完场结算" : pending.category,
      captureHash: pending.capture_identity_hash,
    };
  }
  return card.outcome_tracked
    ? { status: "NOT_CAPTURED", label: "待写入验证 ledger", detail: "已形成验证资格，但尚未看到真实 capture identity。" }
    : { status: "NOT_CAPTURED", label: "本场未进入验证分母", detail: "没有形成分析建议。" };
}

function quoteModel(card: DashboardDayViewCard) {
  const candidate = selectedCandidate(card);
  const evaluatedCandidateRecord = evaluatedCandidate(card);
  const evidence = selectedAnalysisEvidence(card);
  const comparison = record(evidence.comparison);
  const model = record(evidence.model_probability);
  const marketProbability = record(record(evidence.market_probability).devig);
  const quoteIdentity = selectedQuoteIdentity(card);
  const quote = selectedQuote(card);
  const market = text(candidate.market || card.pick?.market);
  const selection = text(candidate.selection || card.pick?.selection);
  if (!market || !selection || !Object.keys(quote).length) return null;
  const normalizedSelection = selection.toUpperCase().replace("_AH", "");
  const mainline = record(evaluatedCandidateRecord.market_mainline);
  const ladderEvaluation = record(evaluatedCandidateRecord.market_ladder_evaluation);
  const evaluatedRows = Array.isArray(ladderEvaluation.candidates)
    ? ladderEvaluation.candidates.map(record)
    : [];
  const oddsEntry = record(record(card.current_odds)[market === "TOTALS" ? "ou" : "ah"]);
  const candidateLines = oddsEntry.candidate_lines;
  const ladder = Array.isArray(candidateLines)
    ? candidateLines.map((raw) => {
      const row = record(raw);
      const lineValue = text(row.line);
      const evaluation = evaluatedRows.find(
        (item) => text(item.line) === lineValue && text(item.selection) === normalizedSelection,
      ) ?? evaluatedRows.find((item) => text(item.line) === lineValue) ?? {};
      return {
        line: lineValue,
        completePairBookmakerCount: numberValue(
          row.complete_pair_bookmaker_count ?? row.bookmaker_count,
        ) ?? 0,
        bookmakerVoteCount: numberValue(row.bookmaker_vote_count) ?? 0,
        leftPrice: numberValue(row.median_over_price ?? row.median_home_price),
        rightPrice: numberValue(row.median_under_price ?? row.median_away_price),
        status: text(row.status || "REJECTED"),
        reason: text(row.reason) || null,
        modelProbability: numberValue(evaluation.model_probability),
        marketProbability: numberValue(evaluation.market_probability),
        probabilityDelta: numberValue(evaluation.probability_delta),
        expectedValue: numberValue(evaluation.expected_value),
        uncertainty: numberValue(evaluation.uncertainty),
      };
    })
    : [];
  const candidateRole = text(evaluatedCandidateRecord.candidate_role) === "ALTERNATE_LINE"
    ? "ALTERNATE_LINE" as const
    : "MARKET_MAINLINE" as const;
  return {
    marketPolicyLabel: text(mainline.selection_policy || "主线政策待确认"),
    candidateRole,
    marketMainlineLine: text(mainline.line || candidate.line),
    marketMainlineBookmakerCount: numberValue(mainline.complete_pair_bookmaker_count) ?? 0,
    marketMainlineVoteCount: numberValue(mainline.bookmaker_vote_count) ?? 0,
    marketMainlineOverPrice: numberValue(mainline.median_over_price),
    marketMainlineUnderPrice: numberValue(mainline.median_under_price),
    marketMainlineHomePrice: numberValue(mainline.median_home_price),
    marketMainlineAwayPrice: numberValue(mainline.median_away_price),
    bookmaker: text(quote.bookmaker_name || quoteIdentity.bookmaker_id || "已审计报价"),
    capturedAt: text(quote.captured_at || quoteIdentity.captured_at),
    marketLabel: marketLabel(market),
    selectionLabel: selectionLabel(market, selection),
    line: text(quote.line || candidate.line || card.pick?.line),
    odds: numberValue(quote.decimal_odds || candidate.odds || card.pick?.odds) ?? 0,
    marketProbability: numberValue(marketProbability[normalizedSelection]),
    modelProbability: numberValue(model.effective_probability),
    probabilityDelta: numberValue(comparison.probability_delta ?? evidence.probability_delta),
    expectedValue: numberValue(model.expected_value ?? evidence.expected_value),
    uncertainty: numberValue(model.ev_se ?? evidence.uncertainty),
    ladder,
  };
}

function fixtureModel(
  card: DashboardDayViewCard,
  performance?: DashboardPerformance,
): DashboardV2FixtureModel {
  const projection = scorelineProjection(card);
  const candidate = selectedCandidate(card);
  const evidence = selectedAnalysisEvidence(card);
  const model = record(evidence.model_probability);
  const quoteIdentity = selectedQuoteIdentity(card);
  const xg = fieldReadiness(card, "xg");
  const ratings = fieldReadiness(card, "ratings");
  const lineups = fieldReadiness(card, "lineups");
  const dynamic = dynamicSnapshot(card);
  const lineupSummary = lineupFacts(card);
  const sourceAbsent = dynamic?.state === "NOT_READY_SOURCE_ABSENT"
    || (
      text(card.reason_code) === "CURRENT_QUOTE_MISSING"
      && (!card.current_odds || Object.keys(card.current_odds).length === 0)
    );
  return {
    fixtureId: card.fixture_id,
    kickoffUtc: card.kickoff_utc ?? "",
    status: card.status ?? "UNKNOWN",
    competition: translateCompetition(card.competition_name || card.competition_id || "比赛"),
    homeTeam: translateTeam(card.home_team_name || "主队"),
    awayTeam: translateTeam(card.away_team_name || "客队"),
    decisionTier: decisionTier(card),
    dataStatus: card.data_status,
    reasonLabel: sourceAbsent
      ? "当前采集窗口尚未取得完整盘口"
      : card.reason_code || card.recommendation_decision_v3?.reason?.message || null,
    nextEvaluationAt: card.next_eval_at ?? null,
    primaryMarketLabel: primaryMarketLabel(card),
    secondaryMarketLabel: secondaryMarketLabel(card),
    scorelineSummary: projection?.status === "READY" ? projection.top3.map((row) => row.scoreline).join(" · ") : null,
    quote: quoteModel(card),
    scorelineProjection: projection,
    modelLabel: text(model.model_version || candidate.model_version || "分析模型"),
    calibrationLabel:
      text(model.calibration_status).toUpperCase() === "BASELINE_PRIOR"
        ? "基线先验模型 · 尚未完成正式校准验证"
        : text(model.calibration_status || "校准状态待确认"),
    dataFacts: [
      `盘口身份 ${text(quoteIdentity.identity_status).toUpperCase() === "COMPLETE" ? "完整" : "待确认"}`,
      `真实 xG ${xg.present === true ? "已就绪" : text(xg.reason_code || "待确认")}`,
      `内部评级 ${ratings.present === true ? "已就绪" : text(ratings.reason_code || "待确认")}`,
      `首发 ${lineups.present === true ? "已就绪" : "未到采集时间"}`,
    ],
    dynamicSnapshot: dynamic,
    lineupFacts: lineupSummary,
    tracking: trackingModel(card, performance),
  };
}

function leagueRows(performance?: DashboardPerformance): DashboardV2LeaguePerformanceRow[] {
  return (performance?.forward_ledger?.performance_cohort.by_league ?? []).map((row) => ({
    competitionKey: row.competition_id || undefined,
    league: translateCompetition(row.league),
    eligibleCount: row.eligible_count,
    hitCount: row.outcomes.hit_count,
    missCount: row.outcomes.miss_count,
    pushCount: row.outcomes.push_count,
    clvMedian: row.clv.median_decimal ?? null,
    clvSampleCount: row.clv.sample_count,
    statusLabel: row.rate_status === "AVAILABLE" ? "观察中" : "样本不足",
  }));
}

export function adaptDashboardV2(
  dayView: DashboardDayView,
  performance: DashboardPerformance | undefined,
  release: ReleaseSyncState | undefined,
): DashboardV2ViewModel {
  const cohort = performance?.forward_ledger?.performance_cohort;
  const fixtures = dayView.cards.map((card) => fixtureModel(card, performance));
  const visibleQuoteTimes = fixtures
    .map((fixture) => fixture.quote?.capturedAt)
    .filter((value): value is string => Boolean(value))
    .sort();
  return {
    observedFootballDay: dayView.football_day,
    release: {
      environment: dayView.environment,
      apiSha: release?.api_git_sha ?? "UNKNOWN",
      webSha: release?.web_git_sha ?? "UNKNOWN",
      pageUpdatedAt: dayView.freshness.page_updated_at ?? dayView.generated_at,
      oddsConfirmedAt:
        visibleQuoteTimes[visibleQuoteTimes.length - 1]
        ?? dayView.freshness.odds_last_confirmed_at
        ?? null,
      nextRefreshAt: dayView.freshness.next_refresh_tick ?? null,
    },
    ledger: {
      rangeLabel: performance?.forward_ledger?.evidence_window.first_capture_at && performance.forward_ledger.evidence_window.latest_capture_at
        ? `${performance.forward_ledger.evidence_window.first_capture_at.slice(5, 10)} 至 ${performance.forward_ledger.evidence_window.latest_capture_at.slice(5, 10)}`
        : "积累中",
      validationCount: cohort?.validation_count ?? 0,
      settledCount: cohort?.processed_count ?? 0,
      pendingCount: cohort?.pending_count ?? 0,
      eligibleCount: cohort?.eligible_count ?? 0,
      evidenceRepairPendingCount: cohort?.excluded_count ?? 0,
      hitCount: cohort?.outcomes.hit_count ?? 0,
      missCount: cohort?.outcomes.miss_count ?? 0,
      pushCount: cohort?.outcomes.push_count ?? 0,
      voidCount: cohort?.outcomes.void_count ?? 0,
      decisiveCount: cohort?.outcomes.decisive_count ?? 0,
      hitRate: cohort?.outcomes.hit_rate ?? null,
      clvMedian: cohort?.clv.median_decimal ?? null,
      clvSampleCount: cohort?.clv.sample_count ?? 0,
    },
    health: {
      automaticCollectionPaused: !dayView.freshness.refreshing && !dayView.freshness.next_refresh_tick,
      competitionCount: new Set(dayView.cards.map((card) => card.competition_id || card.competition_name).filter(Boolean)).size,
      upcomingCount: dayView.cards.filter((card) => !["FT", "AET", "PEN", "FINISHED", "CANCELLED", "POSTPONED"].includes((card.status ?? "").toUpperCase())).length,
      description: !dayView.freshness.refreshing && !dayView.freshness.next_refresh_tick
        ? "当前显示最近冻结快照；下一次受控采集尚未安排。"
        : "赛前数据按真实调度持续更新。",
    },
    fixtures,
    selectedFixtureId: dayView.cards.find((card) => decisionTier(card) === "ANALYSIS_PICK")?.fixture_id ?? dayView.cards[0]?.fixture_id ?? null,
    leaguePerformance: leagueRows(performance),
  };
}
