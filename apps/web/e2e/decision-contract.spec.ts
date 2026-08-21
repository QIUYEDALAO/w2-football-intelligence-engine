import { expect, test, type Page } from "@playwright/test";
import type {
  FixtureFactor,
  IntelligenceWorkspace,
  WorkspaceMarket,
  WorkspaceMatch,
  WorkspaceMatchProjectionError,
  WorkspaceRisks,
  WorkspaceDateStripEntry,
} from "../src/types/intelligenceWorkspace";

type Scenario = "normal" | "limited" | "calm" | "stale" | "empty" | "deployed" | "browser";

function dateStrip(): WorkspaceDateStripEntry[] {
  return Array.from({ length: 15 }, (_, index) => {
    const footballDay = new Date(Date.UTC(2026, 7, 2 + index)).toISOString().slice(0, 10);
    const selected = footballDay === "2026-08-09";
    const future = footballDay > "2026-08-09";
    const fixtureCount = selected ? 3 : future && index % 2 === 0 ? 2 : 0;
    const collectionStatus = fixtureCount
      ? future
        ? "PERSISTED_FIXTURE_OUTSIDE_MARKET_COLLECTION_WINDOW" as const
        : "MARKET_EVIDENCE_AVAILABLE" as const
      : "EMPTY_PERSISTED_DAY" as const;
    return {
      football_day: footballDay,
      fixture_count: fixtureCount,
      competition_count: fixtureCount ? 1 : 0,
      finished_fixture_count: collectionStatus === "MARKET_EVIDENCE_AVAILABLE" ? fixtureCount : 0,
      upcoming_fixture_count: collectionStatus === "MARKET_EVIDENCE_AVAILABLE" ? 0 : fixtureCount,
      persisted_inventory_status: fixtureCount ? "PERSISTED_FIXTURES_AVAILABLE" : "EMPTY_PERSISTED_DAY",
      persisted_competition_coverage_count: fixtureCount ? 1 : 0,
      active_whitelist_count: 13,
      market_collection_window_status: collectionStatus,
      market_evidence_fixture_count: collectionStatus === "MARKET_EVIDENCE_AVAILABLE" ? fixtureCount : 0,
      public_semantics: {
        scope: "SELECTED_DAY",
        cause: collectionStatus === "PERSISTED_FIXTURE_OUTSIDE_MARKET_COLLECTION_WINDOW" ? "NOT_YET_DUE" : null,
      },
    };
  });
}

function risks(): WorkspaceRisks {
  return {
    EVENT_RISK: { dimension: "EVENT_RISK", status: "OK", reason_codes: [], explanation: "当前未见阵容、伤停或比赛事件风险证据。", assessment_status: "ASSESSED_CURRENT" },
    DATA_RISK: { dimension: "DATA_RISK", status: "ATTENTION", reason_codes: ["DATA_FIELD_STALE"], explanation: "大小球走势只有一个已落盘时间快照。", assessment_status: "ASSESSED_CURRENT" },
    MODEL_RISK: { dimension: "MODEL_RISK", status: "ATTENTION", reason_codes: ["MODEL_OUTSIDE_MARKET_RANGE"], explanation: "大小球 2.5 模型落在市场观测区间外。", assessment_status: "ASSESSED_CURRENT" },
    COLLECTION_RISK: { dimension: "COLLECTION_RISK", status: "OK", reason_codes: [], explanation: "当前持久化采集终态未见异常。", assessment_status: "ASSESSED_CURRENT", evidence_basis: "PERSISTED_TERMINAL_ASSESSMENT", source_as_of: "2026-08-09T13:00:00Z" },
  };
}

function market(name: "ASIAN_HANDICAP" | "TOTALS", count: number, candidateQuoteOld = false): WorkspaceMarket {
  const handicap = name === "ASIAN_HANDICAP";
  const lines = handicap ? ["-0.50", "-0.50", "-0.75"] : ["2.50"];
  const sides = handicap ? ["HOME", "AWAY"] : ["OVER", "UNDER"];
  const points = Array.from({ length: count }, (_, index) => ({
    capture_id: `${name.toLowerCase()}-${index + 1}`,
    checkpoint: index === count - 1 ? "T24_OPEN_ODDS" : `T${72 - index * 24}_OPEN_ODDS`,
    captured_at: `2026-08-09T${handicap ? ["06:02", "09:05", "12:11"][index] : "11:48"}:00Z`,
    canonical_line: lines[index] || lines.at(-1) || null,
    bookmaker_count: handicap ? 11 + index + (index > 0 ? 1 : 0) : 6,
    prices: { [sides[0]]: 1.93 + index / 100, [sides[1]]: 1.97 - index / 100 },
    probabilities: { [sides[0]]: 0.5, [sides[1]]: 0.5 },
  }));
  const status = !count ? "INSUFFICIENT" : "READY";
  return {
    market: name,
    status,
    source_status: count ? "READY" : "INSUFFICIENT",
    snapshot_state: !count ? "NO_TIMELINE_EVIDENCE" : count === 1 ? "ONE_OBSERVATION_NOT_A_TREND" : "DISCRETE_REAL_PATH",
    snapshot_count: count,
    observation_count: count * (handicap ? 22 : 12),
    bookmaker_pair_count: points.reduce((sum, point) => sum + point.bookmaker_count, 0),
    quote_row_count: points.reduce((sum, point) => sum + point.bookmaker_count, 0) * 2,
    main_line: count ? lines.at(Math.min(count, lines.length) - 1) || null : null,
    bookmaker_count: points.at(-1)?.bookmaker_count || 0,
    prices: count ? { [sides[0]]: 1.95, [sides[1]]: 1.95 } : {},
    probabilities: count ? { [sides[0]]: 0.5, [sides[1]]: 0.5 } : {},
    quote_age_seconds: count ? 3360 : null,
    timeline_points: points,
    movement: count >= 2 ? {
      status: handicap ? "LINE_MOVEMENT" : "STABLE",
      from_captured_at: points[0].captured_at,
      to_captured_at: points.at(-1)!.captured_at,
      line_delta: handicap ? "-0.25" : "0",
      price_delta: { [sides[0]]: 0.02, [sides[1]]: -0.02 },
      probability_delta: { [sides[0]]: 0.01, [sides[1]]: -0.01 },
    } : { status: "INSUFFICIENT", reason_code: count ? "INSUFFICIENT_SINGLE_SNAPSHOT" : "INSUFFICIENT_NO_TIMELINE_EVIDENCE" },
    reason_codes: count >= 2 ? ["DISCRETE_REAL_PATH"] : [count ? "INSUFFICIENT_SINGLE_SNAPSHOT" : "INSUFFICIENT_NO_TIMELINE_EVIDENCE"],
    trend_evidence_status: count >= 2 ? "AVAILABLE" : "INSUFFICIENT",
    cross_sectional_comparison_status: count ? "AVAILABLE" : "INSUFFICIENT",
    latest_snapshot_at: points.at(-1)?.captured_at || null,
    eligibility: {
      observation_status: count ? "AVAILABLE" : "INSUFFICIENT",
      trend_evidence_status: count >= 2 ? "AVAILABLE" : "INSUFFICIENT",
      cross_sectional_comparison_status: count ? "AVAILABLE" : "INSUFFICIENT",
      model_diagnostic_status: count ? "COMPARABLE_WITHIN_MARKET_RANGE" : "MARKET_NOT_READY",
      candidate_quote_lock_status: count && !candidateQuoteOld ? "READY" : "NOT_READY",
      candidate_model_status: count ? "READY" : "NOT_READY",
      candidate_eligibility_status: count && !candidateQuoteOld ? "READY" : "NOT_READY",
      blockers: count && !candidateQuoteOld ? [] : ["EXECUTABLE_CANDIDATE_QUOTE_NOT_READY"],
    },
  };
}

function checklistMarketFactor(factorId: string, marketName: "ASIAN_HANDICAP" | "TOTALS", rich: boolean, stale: boolean): FixtureFactor {
  const missing = !rich || (factorId === "MK_QUOTE_AGE" && stale);
  const evidence = factorId === "MK_BOOKMAKER_DEPTH"
    ? { source: "market_radar.current", bookmaker_count: rich ? (marketName === "ASIAN_HANDICAP" ? 14 : 6) : 0, minimum_required: 3 }
    : factorId === "MK_QUOTE_AGE"
      ? { source: "market_radar.latest_snapshot_at", quote_age_seconds: rich ? (stale ? 7200 : 600) : null, maximum_seconds: 1800 }
      : { source: "canonical_mainline_identity" };
  return {
    factor_id: factorId,
    display_name_zh: factorId === "MK_EXACT_QUOTE" ? "主盘身份可解析" : factorId === "MK_BOOKMAKER_DEPTH" ? "机构深度" : "报价时效",
    market: marketName,
    role_model_forecast: "NOT_APPLICABLE",
    role_shadow_candidate: "HARD_GATE",
    factor_lifecycle: null,
    numeric_effect_enabled: true,
    state: missing ? "WAITING" : "READY",
    cause: missing ? "NOT_YET_DUE" : null,
    permanence: missing ? "TRANSIENT" : "NOT_APPLICABLE",
    next_window_at: missing ? "2026-08-09T14:30:00Z" : null,
    evidence,
  };
}

function factorChecklist(id: string, rich = false, stale = false): WorkspaceMatch["factor_checklist"] {
  const modelReady = rich;
  const shadowReady = rich && !stale;
  const marketBlockers = shadowReady ? [] : rich ? ["MK_QUOTE_AGE"] : ["MK_EXACT_QUOTE", "MK_BOOKMAKER_DEPTH", "MK_QUOTE_AGE"];
  const blockers = modelReady ? marketBlockers : ["F9_TRUE_XG", ...marketBlockers];
  return {
    fixture_id: id,
    competition_id: "primeira_liga",
    kickoff_utc: "2026-08-09T14:30:00Z",
    as_of: "2026-08-09T13:00:00Z",
    conclusion_zh: modelReady ? shadowReady ? "本场可进入模型预测账本，也具备形成影子候选的输入条件。" : "本场可进入模型预测账本；不能形成影子候选 —— 卡在 报价时效" : "本场不可进入模型预测账本 —— 卡在 四字段 xG（滚动样本不足）",
    market_identity_note_zh: "主盘身份可解析 ≠ 候选报价可锁定；候选轨道还要求报价可执行、候选可用模型及 Decision V4。",
    ledger_fact: { state: "NOT_CAPTURED" },
    enhancement_quality: { state: "READY", missing_factor_ids: [] },
    track_model_forecast: { state: modelReady ? "READY" : "BLOCKED", blocking_factor_ids: modelReady ? [] : ["F9_TRUE_XG"] },
    track_shadow_candidate: {
      state: shadowReady ? "READY" : "BLOCKED",
      blocking_factor_ids: blockers,
      per_market: {
        ASIAN_HANDICAP: { state: shadowReady ? "READY" : "BLOCKED", blocking_factor_ids: blockers },
        TOTALS: { state: shadowReady ? "READY" : "BLOCKED", blocking_factor_ids: blockers },
      },
    },
    factors: [
      { factor_id: "F9_TRUE_XG", display_name_zh: "四字段 xG", market: null, role_model_forecast: "HARD_GATE", role_shadow_candidate: "HARD_GATE", factor_lifecycle: "ACTIVE", numeric_effect_enabled: true, state: modelReady ? "READY" : "MISSING", cause: modelReady ? null : "UNDER_SAMPLED", permanence: modelReady ? "NOT_APPLICABLE" : "SELF_RESOLVING", next_window_at: null, evidence: { source: "rolling_xg_snapshot+team_xg_match", home_sample_count: modelReady ? 3 : 0, away_sample_count: modelReady ? 3 : 0, shortfall: modelReady ? 0 : 3 } },
      ...(["ASIAN_HANDICAP", "TOTALS"] as const).flatMap((marketName) => ["MK_EXACT_QUOTE", "MK_BOOKMAKER_DEPTH", "MK_QUOTE_AGE"].map((factorId) => checklistMarketFactor(factorId, marketName, rich, stale))),
    ],
  };
}

function match(id: string, options: { rich?: boolean; stale?: boolean; modelWarning?: boolean } = {}): WorkspaceMatch {
  const ah = market("ASIAN_HANDICAP", options.rich ? 3 : 0, options.stale);
  const totals = market("TOTALS", options.rich ? 1 : 0, options.stale);
  const reason = options.stale ? null : options.modelWarning ? "MODEL_DIAGNOSTIC" : options.rich ? "MARKET_MOVEMENT" : null;
  const relationStatus = options.modelWarning ? "MODEL_OUTSIDE_MARKET_RANGE" : "COMPARABLE_WITHIN_MARKET_RANGE";
  const relation = (name: "ASIAN_HANDICAP" | "TOTALS") => ({ market: name, status: name === "TOTALS" && options.rich ? "MODEL_OUTSIDE_MARKET_RANGE" : relationStatus, canonical_line: name === "ASIAN_HANDICAP" ? "-0.75" : "2.50", bookmaker_count: name === "ASIAN_HANDICAP" ? 14 : 6, market_quote_age_seconds: 3360, diagnostics: options.modelWarning || (name === "TOTALS" && options.rich) ? [{ status: "OUTSIDE_RANGE" }] : [], blockers: [] });
  const teams: Record<string, [string, string]> = { "1571806": ["Benfica", "Porto"], "1571807": ["Real Madrid", "Real Betis"], "1571808": ["Bayern Munich", "Borussia Dortmund"] };
  const publicTeams: Record<string, [string, string]> = { "1571806": ["本菲卡", "波尔图"], "1571807": ["皇家马德里", "贝蒂斯"], "1571808": ["拜仁慕尼黑", "多特蒙德"] };
  const kickoff: Record<string, string> = { "1571806": "2026-08-09T14:30:00Z", "1571807": "2026-08-09T15:00:00Z", "1571808": "2026-08-09T15:30:00Z" };
  return {
    fixture_id: id,
    competition_id: "primeira_liga",
    competition_name: "Primeira Liga",
    kickoff_utc: kickoff[id] || "2026-08-09T14:30:00Z",
    home_team_name: teams[id]?.[0] || `Home ${id}`,
    away_team_name: teams[id]?.[1] || `Away ${id}`,
    home_team_label: { display_name: publicTeams[id]?.[0] || `主队（身份待确认：${id}-home）`, state: publicTeams[id] ? "CHINESE_LABEL_READY" : "IDENTITY_UNRESOLVED", canonical_team_id: publicTeams[id] ? `w2:${id}:home` : null, provider_team_id: `${id}-home`, public_semantics: { scope: "MATCH", cause: publicTeams[id] ? null : "IDENTITY_UNRESOLVED" }, technical: { raw_provider_name: teams[id]?.[0] || `Home ${id}` } },
    away_team_label: { display_name: publicTeams[id]?.[1] || `客队（身份待确认：${id}-away）`, state: publicTeams[id] ? "CHINESE_LABEL_READY" : "IDENTITY_UNRESOLVED", canonical_team_id: publicTeams[id] ? `w2:${id}:away` : null, provider_team_id: `${id}-away`, public_semantics: { scope: "MATCH", cause: publicTeams[id] ? null : "IDENTITY_UNRESOLVED" }, technical: { raw_provider_name: teams[id]?.[1] || `Away ${id}` } },
    public_semantics: { scope: "MATCH", cause: options.rich ? null : "INSUFFICIENT" },
    status: "NS",
    outcome: { is_finished: false, is_tracked: Boolean(options.rich && !options.stale), is_recorded: false, public_semantics: { scope: "MATCH", cause: "NOT_YET_DUE" } },
    market_collection: { latest_snapshot_at: options.rich ? "2026-08-09T12:11:00Z" : null, latest_snapshot_checkpoint: options.rich ? "T24_OPEN_ODDS" : null, target_checkpoint: "T12_OPEN_ODDS", scheduled_at: "2026-08-09T14:30:00Z", window_end_at: "2026-08-09T14:40:00Z", overdue: false, public_semantics: { scope: "MATCH", cause: "NOT_YET_DUE" } },
    lineup_collection: { target_checkpoint: "T60_ODDS_LINEUPS", scheduled_at: "2026-08-09T13:30:00Z", window_end_at: "2026-08-09T13:50:00Z", overdue: false, public_semantics: { scope: "MATCH", cause: "NOT_YET_DUE" } },
    intelligence_state: options.modelWarning ? "MODEL_DIAGNOSTIC_WARNING" : options.rich ? "MARKET_MOVEMENT" : "DATA_INCOMPLETE",
    intelligence_reason_codes: [options.stale ? "QUOTE_OLDER_THAN_30_MINUTES" : options.modelWarning ? "MODEL_OUTSIDE_MARKET_RANGE" : options.rich ? "MARKET_LINE_MOVEMENT" : "DATA_INCOMPLETE"],
    priority_reason_primary: reason,
    priority_reason_secondary: options.stale ? ["MARKET_MOVEMENT", "CANDIDATE_INPUT_NOT_READY"] : options.rich && !options.modelWarning ? ["MODEL_DIAGNOSTIC"] : options.rich ? [] : ["DATA_INCOMPLETE"],
    factual_summary: options.rich ? `已有当前让球主盘/大小球主盘持久化时间线；可展示已证实走势。已就绪市场可进行模型—市场诊断。${options.stale ? "两个市场的候选输入均未就绪，暂不形成影子候选。" : "两个市场的候选输入均已就绪。"}` : "尚无已落盘让球主盘/大小球主盘市场证据；无法生成走势或当前模型—市场比较；等待既有调度形成证据。",
    risks: risks(),
    readiness: { status: options.rich && !options.stale ? "READY" : "BLOCKED", reason_code: options.stale ? "QUOTE_OLDER_THAN_30_MINUTES" : options.rich ? "EVIDENCE_READY" : "DATA_INCOMPLETE", reason_codes: [], missing_fields: options.rich ? [] : ["market"], stale_fields: options.stale ? ["candidate_quote"] : [], action: "WAIT_FOR_NEXT_SCHEDULED_EVALUATION", next_eval_at: "2026-08-09T13:22:00Z", provider_budget_status: "PROTECTED", lineup_status: "AVAILABLE", lineup_expectation: "ADVISORY", market_aggregate_status: options.rich && !options.stale ? "READY" : "NOT_READY", market_evidence_status: options.rich ? "AVAILABLE" : "NOT_READY", candidate_input_status: options.rich && !options.stale ? "READY" : "NOT_READY" },
    market_fact: { status: ah.status, source_status: ah.source_status, main_line: ah.main_line, current_odds: ah.prices, market_probabilities: ah.probabilities, price_reference: "LAST_AVAILABLE_PREMATCH_SNAPSHOT", canonical_close_status: "NOT_OBTAINABLE_FROM_CURRENT_PROVIDER" },
    w2_analysis: { status: "ANALYSIS_REFERENCE", proof_status: "NOT_PROVEN", decision_tier: "WATCH", analysis_state: relationStatus, reason_codes: [], model_view: { status: "READY", source_status: "READY", model_version: "w2-existing-v1", calibration_version: "cal-v1", calibration_status: "AVAILABLE", simulations_completed: 10_000 }, model_market_relation: { ASIAN_HANDICAP: relation("ASIAN_HANDICAP"), TOTALS: relation("TOTALS") } },
    evaluation_execution: { status: "UNASSESSED", ever_formed_candidate: false, final_states: [], latest_candidates: [], checkpoint_count: 0, market_evaluation_count: 0, checkpoints: [], markets: [], summary_zh: "尚无正式检查点评估", diagnosis: { status: "UNASSESSED", primary_blocker_zh: "尚无权威评估结论", missing_detail_zh: "当前没有足够的候选轨道证据定位原因。", next_step_zh: "查看已注册档位与只读技术证据。", next_checkpoint: null, next_checkpoint_at: null, non_blocking_missing_zh: [], evidence_codes: [] } },
    shadow_candidate: options.rich && !options.stale ? { status: "ACTIVE", mode: "SHADOW_ONLY", authority: "RECOMMENDATION_DECISION_V4", decision_tier: "ANALYSIS_PICK", reason_code: "ANALYSIS_ONLY", reason_message: "当前仅提供影子候选", market: "ASIAN_HANDICAP", selection: "HOME", exact_line: "-0.75", decimal_odds: 1.95, captured_at: "2026-08-09T12:11:00Z", decision_hash: "a".repeat(64), recommendation_scope: "VALIDATION", outcome_tracked: true, formal_status: "OFF", lock_status: "OFF", production_action_allowed: false, real_money_allowed: false } : { status: "NOT_READY", mode: "SHADOW_ONLY", authority: "RECOMMENDATION_DECISION_V4", decision_tier: "NOT_READY", reason_code: "EVIDENCE_NOT_READY", reason_message: "当前证据尚未就绪", market: null, selection: null, exact_line: null, decimal_odds: null, captured_at: null, decision_hash: null, recommendation_scope: "NONE", outcome_tracked: false, formal_status: "OFF", lock_status: "OFF", production_action_allowed: false, real_money_allowed: false },
    factor_checklist: factorChecklist(id, options.rich, options.stale),
    formal_recommendation: { status: "OFF", reason: "PRODUCT_AUTHORITY_DISABLED" },
    market_radar: { schema_version: "w2.market-radar.v1", markets: { ASIAN_HANDICAP: ah, TOTALS: totals } },
    model_lab: { schema_version: "w2.model-lab.v1", w2_model: { status: "READY", source_status: "READY", model_version: "w2-existing-v1", calibration_status: "AVAILABLE" }, market: { ASIAN_HANDICAP: { status: ah.status, source_status: ah.source_status, main_line: ah.main_line, bookmaker_count: ah.bookmaker_count, quote_age_seconds: ah.quote_age_seconds }, TOTALS: { status: totals.status, source_status: totals.source_status, main_line: totals.main_line, bookmaker_count: totals.bookmaker_count, quote_age_seconds: totals.quote_age_seconds } }, api_football_prediction: { status: "NOT_AVAILABLE", role: "EXTERNAL_MODEL_BENCHMARK", reason_code: "API_FOOTBALL_PREDICTION_NOT_PROJECTED" }, relation: { ASIAN_HANDICAP: relation("ASIAN_HANDICAP"), TOTALS: relation("TOTALS") }, historical_validation: { final_verdict: "NO_EDGE", reexecuted: false } },
    scoreline_reference: options.rich && !options.stale ? { label: "MODEL_SCORELINE_REFERENCE", proof_status: "NOT_PROVEN", status: "READY", simulations_completed: 10_000, top3: [{ scoreline: "1-1", unconditional_probability: .126, sample_count: 1260 }, { scoreline: "2-1", unconditional_probability: .101, sample_count: 1010 }, { scoreline: "1-0", unconditional_probability: .094, sample_count: 940 }] } : { label: "MODEL_SCORELINE_REFERENCE", proof_status: "NOT_PROVEN", status: "UNAVAILABLE", simulations_completed: null, top3: [] },
    evidence: { card_hash: `card-${id}`, artifact_hash: `artifact-${id}`, source: "decision_contract", source_event_at: "2026-08-09T13:00:00Z", decision_role: "DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY" },
  };
}

function modelForecastValidation(): IntelligenceWorkspace["validation"]["model_forecast"] {
  const buckets = {
    LT_6H: { capture_count: 1, settled_count: 0, pending_count: 1 },
    H6_TO_LT_24H: { capture_count: 4, settled_count: 1, pending_count: 3 },
    D1_TO_D3: { capture_count: 7, settled_count: 7, pending_count: 0 },
    GT_3D: { capture_count: 1, settled_count: 0, pending_count: 1 },
  };
  return {
    capture_count: 13,
    settled_count: 8,
    pending_count: 5,
    sample_target: 200,
    current_flow_candidate_count: 0,
    current_flow_settled_count: 0,
    ever_formed_candidate_count: 0,
    final_candidate_count: 0,
    invalidated_candidate_count: 0,
    t30_evaluated_candidate_count: 0,
    t30_confirmed_candidate_count: 0,
    min_xg_matches: 3,
    xg_ready_team_count: 128,
    next_7d_xg_ready_fixture_count: 36,
    capture_policy: "FIRST_ELIGIBLE_FREEZE_IMMUTABLE",
    market_evaluation_funnel: { scope: "CHECKPOINT_EVALUATION_OPPORTUNITY_V2", denominator_unit: "CHECKPOINT_EVALUATION_OPPORTUNITY_SLOT_X_MARKET", measurement_status: "MEASURABLE", invalid_opportunity_row_count: 0, invalid_opportunity_reasons: {}, opportunity_count: 10, capture_count: 3, fixture_count: 3, market_unit_count: 6, persisted_market_unit_count: 6, recorded_at_count: 10, gate_counts: { model_ready: 10, mainline_parsed: 8, bookmaker_depth: 7, quote_fresh: 6, evaluated: 6, no_edge: 4, candidate: 2 }, gate_rates: { model_ready: 1, mainline_parsed: 0.8, bookmaker_depth: 0.7, quote_fresh: 0.6, evaluated: 0.6, no_edge: 0.4, candidate: 0.2 }, first_failed_gate_counts: { bookmaker_depth: 1, quote_fresh: 1 } },
    lead_time_buckets: buckets,
    official_recommendations: [],
    data_versions: {
      TEAM_XG_MATCH_ROWS_1868: {
        team_xg_match_count: 1868,
        capture_count: 13,
        settled_count: 8,
        pending_count: 5,
        lead_time_buckets: buckets,
      },
    },
    public_semantics: { scope: "CROSS_DAY_CUMULATIVE", cause: null },
  };
}

function workspace(scenario: Scenario = "normal"): IntelligenceWorkspace {
  const rich = match("1571806", { rich: true, stale: scenario === "stale" });
  const other = [match("1571807", { rich: true }), match("1571808", { modelWarning: true })];
  const deployedMatches = [match("1571807"), match("1571806", { rich: true, stale: true }), match("1571808")];
  const calmMatches = Array.from({ length: 9 }, (_, index) => {
    const item = match(`calm-${index}`, { rich: true });
    item.competition_id = `calm-league-${index % 7}`;
    item.competition_name = `Calm League ${index % 7}`;
    item.priority_reason_primary = null;
    item.priority_reason_secondary = [];
    item.intelligence_state = "MARKET_STABLE";
    item.intelligence_reason_codes = ["MARKET_STABLE"];
    return item;
  });
  const browserMatches = Array.from({ length: 11 }, (_, index) => {
    const item = match(`browser-${index}`, { rich: true, stale: index === 0 });
    item.competition_id = `browser-league-${index % 7}`;
    item.competition_name = `Browser League ${index % 7}`;
    if (index > 1) {
      item.priority_reason_primary = null;
      item.priority_reason_secondary = [];
      item.intelligence_state = "MARKET_STABLE";
      item.intelligence_reason_codes = ["MARKET_STABLE"];
    }
    return item;
  });
  const matches = scenario === "deployed"
    ? deployedMatches
    : scenario === "normal" || scenario === "stale"
      ? [other[0], rich, other[1]]
      : scenario === "limited"
        ? [match("1571807"), match("1571808")]
        : scenario === "calm"
          ? calmMatches
          : scenario === "browser"
            ? browserMatches
          : [];
  const limited = scenario === "limited";
  const empty = scenario === "empty";
  const focusId = scenario === "browser" ? "browser-0" : scenario === "normal" || scenario === "stale" || scenario === "deployed" ? "1571806" : null;
  const counts = scenario === "browser" ? { MARKET_MOVEMENT: 1 } : focusId ? scenario === "deployed" ? {} : scenario === "stale" ? { MARKET_MOVEMENT: 1, MODEL_DIAGNOSTIC: 1 } : { MARKET_MOVEMENT: 2, MODEL_DIAGNOSTIC: 1 } : {};
  const globalFocus = focusId ? null : {
    reason_code: limited ? "AWAITING_COLLECTION" : scenario === "calm" ? "NO_PRIORITY_REVIEW_ITEMS" : "NO_FIXTURES_IN_FOOTBALL_DAY",
    factual_summary: limited ? "所选比赛日暂无可用于比赛级分析的持久化市场证据。" : scenario === "calm" ? "当前没有达到优先复核条件的比赛。" : "本比赛日观察池内没有比赛；不会从其他日期填充。",
    affected_fixture_count: limited ? matches.length : 0,
    affected_competition_count: limited ? 1 : 0,
    source_as_of: "2026-08-09T13:05:00Z",
    next_eval_at: scenario === "calm" || limited ? "2026-08-09T14:49:00Z" : null,
    recovery_condition: limited ? "等待既有调度形成新的持久化市场快照；本页不调用 Provider。" : null,
    public_semantics: { scope: "SELECTED_DAY" as const, cause: limited ? "AWAITING_COLLECTION" as const : null },
  };
  const strip = dateStrip();
  const selectedStrip = strip[7];
  const selectedCompetitionCount = new Set(matches.map((item) => item.competition_id)).size;
  selectedStrip.fixture_count = matches.length;
  selectedStrip.competition_count = selectedCompetitionCount;
  selectedStrip.finished_fixture_count = matches.filter((item) => item.outcome.is_finished).length;
  selectedStrip.upcoming_fixture_count = matches.length - selectedStrip.finished_fixture_count;
  selectedStrip.persisted_inventory_status = matches.length ? "PERSISTED_FIXTURES_AVAILABLE" : "EMPTY_PERSISTED_DAY";
  selectedStrip.persisted_competition_coverage_count = selectedCompetitionCount;
  selectedStrip.market_collection_window_status = matches.length ? "MARKET_EVIDENCE_AVAILABLE" : "EMPTY_PERSISTED_DAY";
  selectedStrip.market_evidence_fixture_count = matches.length;
  selectedStrip.public_semantics = { scope: "SELECTED_DAY", cause: null };
  if (limited) {
    for (const item of matches) item.public_semantics = { scope: "MATCH", cause: "AWAITING_COLLECTION" };
    strip[7].market_collection_window_status = "MARKET_COLLECTION_DUE_EVIDENCE_NOT_READY";
    strip[7].market_evidence_fixture_count = 0;
    strip[7].public_semantics = { scope: "SELECTED_DAY", cause: "AWAITING_COLLECTION" };
  }
  const trackedFixtureIds = matches.filter((item) => item.outcome.is_tracked).map((item) => item.fixture_id);
  return {
    request_id: `v41-${scenario}`,
    schema_version: "w2.dashboard-intelligence-workspace.v1",
    generated_at: "2026-08-09T13:07:00Z",
    date: "2026-08-09",
    timezone: "Asia/Shanghai",
    window: "today",
    football_day_timezone: "Asia/Shanghai",
    football_day_cutoff_hour: 12,
    football_day_start_utc: "2026-08-09T04:00:00Z",
    football_day_end_utc: "2026-08-10T04:00:00Z",
    source: "dashboard_day_view+performance_checkpoint+replay_front_door",
    selected_fixture_id: focusId,
    today_summary: { match_count: matches.length, competition_count: selectedCompetitionCount, priority_match_count: Object.values(counts).reduce((sum, count) => sum + count, 0), priority_group_count: Object.keys(counts).length, primary_reason_counts: counts, pending_owner_review_team_count: 0 },
    global_focus: globalFocus,
    global_model_quality: { status: "AVAILABLE", checkpoint_key: "performance:cohort:all", checkpoint_generated_at: "2026-08-09T12:00:00Z", freshness_max_age_seconds: 86_400, model_log_loss: .512, market_log_loss: .508, model_brier: .178, market_brier: .174, model_calibration_error: .026, sample_count: 34 },
    read_contract: { provider_calls: 0, db_writes: 0, would_write_checkpoint: false, no_call_on_read: true },
    runtime: {
      product: "FOOTBALL_MARKET_INTELLIGENCE_PLUS_MODEL_DIAGNOSTICS",
      public_dashboard_authority: "NEW_INTELLIGENCE_WORKSPACE_ONLY",
      active_whitelist_count: 13,
      free_bridge_mode: "SHADOW_ONLY",
      market_price_attention_threshold_ratio: 0.02,
      candidate: "SHADOW_ONLY",
      formal: "OFF",
      lock: "OFF",
      production: "OFF",
      recommendation_capabilities: {
        analysis_ah: { implementation: "CODE_PRESENT", feature_enabled: true },
        analysis_ou: { implementation: "CODE_PRESENT", feature_enabled: true },
        shadow_candidate: { implementation: "CODE_PRESENT", feature_enabled: true },
        formal_ah: { implementation: "CODE_PRESENT", feature_enabled: false },
        formal_ou: { implementation: "NOT_IMPLEMENTED", feature_enabled: false },
        production_recommendation: { implementation: "CODE_PRESENT", feature_enabled: false },
      },
    },
    navigation: { current_date: "2026-08-09", previous_date: "2026-08-08", next_date: "2026-08-10", next_available_date: "2026-08-10" },
    date_strip: strip,
    attention: matches.map((item) => ({ fixture_id: item.fixture_id, kickoff_utc: item.kickoff_utc, intelligence_state: item.intelligence_state, reason_codes: item.intelligence_reason_codes, affected_domains: ["MARKET"], factual_summary: item.intelligence_reason_codes.join("；"), readiness_status: item.readiness.status, readiness_context: { reason_code: item.readiness.reason_code, missing_fields: item.readiness.missing_fields, stale_fields: item.readiness.stale_fields, action: item.readiness.action }, next_eval_at: item.readiness.next_eval_at, risks: item.risks })),
    matches,
    validation: { probability: { status: "AVAILABLE", sample_count: 34, model_brier: .178, market_brier: .174, model_minus_market_brier: .004, model_log_loss: .512, market_log_loss: .508, model_minus_market_log_loss: .004, model_calibration_error: .026, market_calibration_error: .021, model_reliability_bins: [], market_reliability_bins: [], checkpoint_metadata: { checkpoint_key: "performance:cohort:all" } }, directional: { status: "SAMPLE_BUILDING", source_status: "AVAILABLE", probability_evidence_ready: false, validation_n: 36, decisive_n: 34, correct: 18, wrong: 16, push: 1, void: 1, direction_accuracy: 18 / 34, effective_n: 34, market_direction_benchmark: "NOT_DEFINED", only_record_reason: "PROBABILITY_QUALITY_NOT_READY" }, league_performance: [], tournament_performance: [], model_forecast: modelForecastValidation(), forward_validation_records: { status: "AVAILABLE", validation_count: 36, eligible_count: 34, excluded_count: 2, excluded_share: 2 / 36, excluded_by_reason: { MARKET_IDENTITY_NOT_READY: 2 }, pending_count: 0, outcomes: {}, checkpoint_metadata: { checkpoint_key: "performance:cohort:all" }, public_semantics: { scope: "CROSS_DAY_CUMULATIVE", cause: null } }, history_replay: { status: matches.length ? "FORWARD_RECORD" : "EMPTY", known_at: { has_day_view: true }, decision_summary: { total_cards: matches.length, lock_eligible_count: 0, by_decision_tier: { WATCH: matches.length }, by_data_status: { READY: matches.length } }, reason_summary: [], outcome_tracking_summary: { tracked_fixture_ids: trackedFixtureIds, matched_fixture_ids: [], missing_outcome_fixture_ids: [], tracked_count: trackedFixtureIds.length, matched_outcome_count: 0, missing_outcome_count: 0 }, card_hash_checks: [], replay_gaps: [], record_kind: matches.length ? "FORWARD_RECORD" : "EMPTY", public_semantics: { scope: "SELECTED_DAY", cause: matches.length ? "NOT_YET_DUE" : null } } },
    external_intelligence: { weather: { status: "NOT_CONNECTED", affects_match_readiness: false }, news: { status: "NOT_CONNECTED", affects_match_readiness: false }, sentiment: { status: "NOT_CONNECTED", affects_match_readiness: false }, advanced_xg: { status: "NOT_CONNECTED", affects_match_readiness: false } },
    freshness: { domains: {} },
    data_operations: { read_model_source: "dashboard_read_model", checkpoint_key: "dashboard:day_view:2026-08-09", degradation: { state: limited || scenario === "deployed" ? "BLOCKED_DAY" : empty ? "EMPTY_DAY" : "HEALTHY" }, counts: { total: matches.length }, system_health: limited || scenario === "deployed" ? "BLOCKED_DAY" : "HEALTHY", provider_budget_status: "PROTECTED" },
  };
}

async function installWorkspace(page: Page, scenario: Scenario = "normal"): Promise<void> {
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: workspace(scenario) }));
}

test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-08-09T13:07:00Z"));
});

test("public team labels come from the workspace authority, not frontend guessing", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  await expect(page.locator(".v41-focus-header h1")).toHaveText("本菲卡 vs 波尔图");
  await expect(page.locator(".v41-focus-header h1")).not.toContainText("Benfica");
});

test("future selected day derives neutral scope/cause copy and keeps known raw team names", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-08-11T06:44:00Z"));
  const payload = workspace("limited");
  payload.date = "2026-08-14";
  payload.generated_at = "2026-08-11T06:44:00Z";
  payload.football_day_start_utc = "2026-08-14T04:00:00Z";
  payload.football_day_end_utc = "2026-08-15T04:00:00Z";
  payload.navigation = {
    current_date: payload.date,
    previous_date: "2026-08-13",
    next_date: "2026-08-15",
    next_available_date: "2026-08-15",
  };
  payload.global_focus!.public_semantics = { scope: "SELECTED_DAY", cause: "NOT_YET_DUE" };
  payload.global_focus!.next_eval_at = null;
  payload.validation.history_replay.record_kind = "FORWARD_RECORD";
  payload.validation.history_replay.public_semantics = { scope: "SELECTED_DAY", cause: "NOT_YET_DUE" };
  payload.matches[0].kickoff_utc = "2026-08-14T12:00:00Z";
  payload.matches[0].home_team_label = { display_name: "Rosenborg", state: "CANONICAL_IDENTITY_READY_LABEL_MISSING", canonical_team_id: "w2:team:api_football:331", provider_team_id: "331", public_semantics: { scope: "MATCH", cause: "LABEL_MISSING" }, technical: { raw_provider_name: "Rosenborg" } };
  payload.matches[0].away_team_label = { display_name: "维京", state: "CHINESE_LABEL_READY", canonical_team_id: "w2:team:api_football:759", provider_team_id: "759", public_semantics: { scope: "MATCH", cause: null }, technical: { raw_provider_name: "Viking" } };
  payload.matches[1].kickoff_utc = "2026-08-14T17:00:00Z";
  const selected = payload.date_strip.find((item) => item.football_day === payload.date)!;
  selected.fixture_count = 2;
  selected.upcoming_fixture_count = 2;
  selected.competition_count = 1;
  selected.persisted_competition_coverage_count = 1;
  selected.persisted_inventory_status = "PERSISTED_FIXTURES_AVAILABLE";
  selected.market_collection_window_status = "PERSISTED_FIXTURE_OUTSIDE_MARKET_COLLECTION_WINDOW";
  selected.public_semantics = { scope: "SELECTED_DAY", cause: "NOT_YET_DUE" };
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));

  await page.goto("/");
  await page.getByLabel("选择比赛日").fill(payload.date);
  await expect(page.getByLabel("选择比赛日")).toHaveValue(payload.date);

  const selectedDayCause = page.locator("header.v41-header [data-public-cause=NOT_YET_DUE]");
  await expect(selectedDayCause).toHaveText("W2 计划采集尚未开始");
  await expect(selectedDayCause).toHaveClass(/v41-pill--neutral/);
  await expect(page.locator(".v41-shortlist .v41-stripe--neutral")).toHaveCount(2);
  await expect(page.locator(".v41-shortlist [class*='collection_incident']")).toHaveCount(0);
  await expect(page.locator("body")).not.toContainText("采集异常");
  await expect(page.locator(".v41-today")).toContainText("场所选比赛日比赛");
  await expect(page.locator(".v41-global h1")).toContainText("W2 计划采集尚未开始");
  await expect(page.locator(".v41-global-note")).toContainText("不判断外部市场是否已有盘口");
  await expect(page.locator(".v41-shortlist")).toContainText("Rosenborg");
  await expect(page.locator(".v41-shortlist")).toContainText("维京");
  await expect(page.locator(".v41-shortlist")).toContainText("中文译名待映射");
  await expect(page.locator(".v41-shortlist")).not.toContainText("主队（中文译名待映射）");
  await expect(page.locator("body")).not.toContainText("仅赛程");
  await expect(page.locator(".v41-shortlist time").first()).toHaveText("20:00");
  await expect(page.locator(".v41-shortlist time").nth(1)).toHaveText("次日 01:00");
  await expect(page.locator("#secondary-validation")).toContainText("前向记录");
  await expect(page.locator("#secondary-validation")).toContainText("赛果尚未产生");
  await expect(page.locator("#secondary-validation")).not.toContainText("赛果匹配 / 缺失");
});

test("cross-day cumulative insufficiency never becomes a selected-day failure", async ({ page }) => {
  const payload = workspace("normal");
  payload.validation.forward_validation_records.public_semantics = { scope: "CROSS_DAY_CUMULATIVE", cause: "INSUFFICIENT" };
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));

  await page.goto("/");

  await expect(page.locator(".v41-validation-verdict")).toContainText("样本量远不足以判断模型好坏");
  await expect(page.locator(".v41-validation-verdict")).not.toContainText("所选比赛日");
});

test("V41 uses the selected fixture fact and never falls back to matches[0]", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  await expect(page.locator(".dashboard-v41")).toHaveAttribute("data-public-cause", "NONE");
  await expect(page.locator(".v41-focus")).toHaveAttribute("data-fixture-id", "1571806");
  await expect(page.locator(".v41-shortlist-list button").first()).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".v41-focus h1")).toContainText("本菲卡");
  await expect(page.locator(".v41-shortlist > header")).toContainText("赔率相对变化 ≥ 2%");
  await expect(page.getByLabel("选择比赛日")).toHaveValue(/^\d{4}-\d{2}-\d{2}$/);
  await expect(page.locator(".v41-today-day")).toContainText("比赛日 2026-08-09 12:00 → 2026-08-10 12:00（不含）");
});

test("shadow candidate is explicit, tracked and non-production", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");

  await expect(page.getByText("影子候选已启用", { exact: true })).toBeVisible();
  await expect(page.locator(".v41-candidate")).toHaveAttribute("data-candidate-status", "ACTIVE");
  await expect(page.locator(".v41-candidate")).toContainText("让球主盘 · 推荐主队");
  await expect(page.locator(".v41-candidate")).toContainText("推荐主队盘口 0.75 · 赔率 1.95");
  await expect(page.locator(".v41-candidate")).toContainText("Formal、Lock、Production 与实盘保持关闭");
  await expect(page.locator("#secondary-validation .v41-validation-t30")).toContainText("T-30 候选评估0");
});

test("V41 presents unassessed model evidence in Chinese and keeps codes technical", async ({ page }) => {
  const payload = workspace();
  const focused = payload.matches.find((item) => item.fixture_id === payload.selected_fixture_id)!;
  focused.w2_analysis.model_view.status = "PRIOR_ONLY";
  focused.model_lab.w2_model.status = "PRIOR_ONLY";
  for (const relation of Object.values(focused.w2_analysis.model_market_relation)) {
    relation.status = "MODEL_NOT_READY";
    relation.blockers = ["MODEL_CALIBRATION_NOT_READY"];
  }
  for (const market of Object.values(focused.market_radar.markets)) {
    market.eligibility.model_diagnostic_status = "MODEL_NOT_READY";
    market.eligibility.candidate_model_status = "NOT_READY";
    market.eligibility.candidate_eligibility_status = "NOT_READY";
    market.eligibility.blockers = ["MODEL_CALIBRATION_NOT_READY"];
  }
  focused.readiness.market_aggregate_status = "NOT_READY";
  focused.readiness.candidate_input_status = "NOT_READY";
  focused.factual_summary = "已有当前让球主盘/大小球主盘持久化时间线；可展示已证实走势。可比较模型尚未就绪（需已验证校准），暂不进行模型—市场比较。两个市场的候选输入均未就绪，暂不形成影子候选。";
  focused.risks.MODEL_RISK = {
    dimension: "MODEL_RISK",
    status: "ATTENTION",
    reason_codes: ["MODEL_SIMULATION_NOT_READY"],
    explanation: "可比较模型尚无已验证校准证据",
    assessment_status: "UNASSESSED",
  };
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");

  await expect(page.locator(".v41-three-layer")).toContainText("逐市场 · 均未就绪");
  await expect(page.locator(".v41-three-layer")).not.toContainText("部分就绪");
  await expect(page.locator(".v41-focus-summary")).toContainText("尚无权威评估结论");
  await expect(page.locator(".v41-focus-summary")).not.toContainText("ASIAN_HANDICAP/TOTALS");
  await expect(page.locator(".v41-market-details")).toContainText("可用模型");
  await expect(page.locator("[data-market-details='ASIAN_HANDICAP']")).toContainText("尚未就绪");
  const modelDiagnostic = page.locator(".v41-diagnostic").filter({ hasText: "可比较模型（需已验证校准）" });
  await expect(modelDiagnostic).toContainText("可比较模型（需已验证校准）");
  await expect(modelDiagnostic).not.toContainText("当前模型状态");
  await expect(modelDiagnostic).not.toContainText("MODEL_NOT_READY");
  await expect(page.locator(".v41-risk-list")).toContainText("可比较模型校准尚无已验证校准可比较模型尚无已验证校准证据");
  await expect(page.getByText("MODEL_CALIBRATION_NOT_READY", { exact: true })).not.toBeVisible();
});

test("market depth asymmetry stays inside the existing technical details", async ({ page }) => {
  const payload = workspace();
  const focused = payload.matches.find((item) => item.fixture_id === payload.selected_fixture_id)!;
  focused.market_radar.markets.ASIAN_HANDICAP.reason_codes.push("MARKET_DEPTH_ASYMMETRY");
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");

  const focus = page.locator(".v41-focus");
  const reason = focus.getByText("ASIAN_HANDICAP:MARKET_DEPTH_ASYMMETRY", { exact: true });
  await expect(reason).not.toBeVisible();
  await focus.locator(".v41-compact-audit > summary").click();
  await focus.locator(".v41-details > summary").click();
  await expect(reason).toBeVisible();
  await expect(focus.locator(".v41-focus-summary")).not.toContainText("MARKET_DEPTH_ASYMMETRY");
});

test("raw system health cannot override collection windows or candidate quote age", async ({ page }) => {
  await installWorkspace(page, "deployed");
  await page.goto("/");
  await expect(page.locator(".dashboard-v41")).toHaveAttribute("data-public-cause", "NONE");
  await expect(page.locator("header.v41-header")).toContainText("市场证据可用");
  await expect(page.locator("header.v41-header")).not.toContainText("BLOCKED DAY");
  await expect(page.locator(".v41-focus")).toHaveAttribute("data-fixture-id", "1571806");
  await expect(page.locator(".v41-shortlist > header")).toContainText("0 场优先");
  await expect(page.locator(".v41-shortlist-list")).not.toContainText("证据已过期");
  await expect(page.locator(".v41-shortlist-list")).toContainText("关注 · 尚无权威评估结论");
  await expect(page.locator(".v41-shortlist-list")).toContainText("其他关注 · 3 场（不计入优先）");
  await expect(page.locator(".v41-focus-summary")).toContainText("尚无权威评估结论");
});

for (const [scenario, cause, copy] of [
  ["limited", "AWAITING_COLLECTION", "今日比赛可查看，已到采集时点，证据待采集"],
  ["calm", "NONE", "9 场比赛未触发优先复核"],
  ["empty", "NONE", "所选比赛日没有纳入观察池的比赛"],
] as const) {
  test(`V41 ${scenario} renders facts plus the single public cause`, async ({ page }) => {
    await installWorkspace(page, scenario);
    await page.goto("/");
    await expect(page.locator(".dashboard-v41")).toHaveAttribute("data-public-cause", cause);
    await expect(page.locator(".v41-focus")).toContainText(copy);
    await expect(page.locator(".v41-focus")).not.toHaveAttribute("data-fixture-id", /.+/);
  });
}

test("V41 separates diagnostic market age from the candidate quote-age hard gate", async ({ page }) => {
  const payload = workspace("stale");
  payload.matches.find((item) => item.fixture_id === payload.selected_fixture_id)!.kickoff_utc = "2026-08-10T14:30:00Z";
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");
  const totals = page.locator("[data-market='TOTALS']");
  await expect(page.locator("[data-market-details='TOTALS']")).toContainText("证据不足");
  await expect(page.locator(".v41-market-details")).toContainText("同一时刻机构双边报价可比较");
  await expect(page.locator(".v41-focus-summary")).toContainText("尚无权威评估结论");
  await expect(page.locator(".v41-three-layer")).toContainText("市场输入报价证据逐市场 · 均未就绪");
  await expect(page.locator(".v41-candidate")).toHaveCount(0);
  await expect(page.locator(".v41-snapshots time").first()).toHaveText("08-09 14:02");
  await expect(page.locator(".v41-scoreline")).toHaveCount(0);
});

test("AH market radar uses the owner main-handicap sign convention", async ({ page }) => {
  const payload = workspace();
  const focused = payload.matches.find((item) => item.fixture_id === payload.selected_fixture_id)!;
  const handicap = focused.market_radar.markets.ASIAN_HANDICAP;
  handicap.main_line = "0.5";
  handicap.timeline_points = handicap.timeline_points.map((point) => ({
    ...point,
    canonical_line: "0.5",
    prices: { HOME: 1.94, AWAY: 1.80 },
  }));
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");

  const market = page.locator("[data-market='ASIAN_HANDICAP']");
  await expect(market.locator("[data-market-line]")).toHaveText("-0.5");
  await expect(market.locator(".v41-snapshots li").last()).toContainText("-0.5");
  await expect(market.locator(".v41-snapshots li").last()).toContainText("主 1.94 / 客 1.80");
  await expect(page.locator(".v41-three-layer > div").first()).toContainText("-0.5");

  handicap.main_line = "-1.5";
  handicap.timeline_points = handicap.timeline_points.map((point) => ({ ...point, canonical_line: "-1.5" }));
  await page.reload();
  await expect(market.locator("[data-market-line]")).toHaveText("1.5");
  await expect(market.locator(".v41-snapshots li").last()).toContainText("1.5");
});

test("AH recommendation rows share the owner main-handicap sign convention with market radar", async ({ page }) => {
  const payload = workspace();
  const focused = payload.matches.find((item) => item.fixture_id === payload.selected_fixture_id)!;
  focused.fixture_id = "1490405";
  focused.market_radar.markets.ASIAN_HANDICAP.main_line = "-0.5";
  payload.selected_fixture_id = focused.fixture_id;
  const recommendations = [
    ["1490398", "AWAY", "-0.5", "让球 -0.5 · 推荐客队"],
    ["1490400", "HOME", "+0.25", "让球 -0.25 · 推荐主队"],
    ["1490401", "AWAY", "+0.75", "让球 0.75 · 推荐客队"],
    ["1490402", "AWAY", "+0.5", "让球 0.5 · 推荐客队"],
    ["1490404", "AWAY", "+1.0", "让球 1.0 · 推荐客队"],
    ["1490405", "HOME", "-0.5", "让球 0.5 · 推荐主队"],
  ] as const;
  payload.validation.model_forecast.official_recommendations = recommendations.map(([fixtureId, selection, exactLine], index) => ({
    evaluation_id: `eval-${fixtureId}`,
    fixture_id: fixtureId,
    evaluated_at: `2026-08-10T01:0${index}:00Z`,
    kickoff_utc: "2026-08-10T02:00:00Z",
    market: "ASIAN_HANDICAP",
    selection,
    exact_line: exactLine,
    decimal_odds: 1.88,
    home_team_label: focused.home_team_label,
    away_team_label: focused.away_team_label,
    score: null,
    settlement: "PENDING",
    profit_units: null,
  }));
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");

  for (const [fixtureId, , , expected] of recommendations) {
    await expect(page.locator(`.v41-official-recommendations li[data-fixture-id='${fixtureId}'] > span`).first()).toHaveText(expected);
  }
  const radarLine = await page.locator("[data-focus-type='MATCH'] [data-market='ASIAN_HANDICAP'] [data-market-line]").textContent();
  const recommendationText = await page.locator(".v41-official-recommendations li[data-fixture-id='1490405'] > span").first().textContent();
  expect(recommendationText).toContain(`让球 ${radarLine}`);
});

test("quote age gate mark reads each market's projected maximum", async ({ page }) => {
  const payload = workspace();
  const focused = payload.matches.find((item) => item.fixture_id === payload.selected_fixture_id)!;
  focused.market_radar.markets.ASIAN_HANDICAP.quote_age_seconds = 120;
  focused.market_radar.markets.TOTALS.quote_age_seconds = 121;
  for (const factor of focused.factor_checklist.factors) {
    if (factor.factor_id === "MK_QUOTE_AGE") factor.evidence.maximum_seconds = 120;
  }
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");

  const ready = page.locator("[data-market='ASIAN_HANDICAP'] [data-quote-age-state='ready']");
  const warning = page.locator("[data-market='TOTALS'] [data-quote-age-state='warning']");
  await expect(ready).toContainText("快照年龄2 分钟✓");
  await expect(ready.locator(".v41-quote-age-mark")).toHaveCSS("color", "rgb(111, 166, 135)");
  await expect(warning).toContainText("快照年龄2 分钟✗");
  await expect(warning.locator(".v41-quote-age-mark")).toHaveCSS("color", "rgb(203, 160, 90)");
});

test("1440x900 keeps the actionable market chain and final candidate state above the fold", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await installWorkspace(page);
  await page.goto("/");

  const market = page.locator("[data-focus-type='MATCH'] [data-market='ASIAN_HANDICAP']");
  const targets = [
    market.locator("[data-market-line]"),
    market.locator(".v41-snapshots li.is-latest span"),
    market.locator(".v41-market-summary > div").nth(1),
    market.locator("[data-quote-age-state]"),
    page.locator("[data-focus-type='MATCH'] [data-diagnosis-status]"),
  ];
  for (const target of targets) {
    await expect(target).toBeVisible();
    const bottom = await target.evaluate((node) => node.getBoundingClientRect().bottom);
    expect(bottom).toBeLessThanOrEqual(900);
  }
});

test("V41 keeps low-priority diagnostics folded by default", async ({ page }) => {
  await installWorkspace(page, "deployed");
  await page.goto("/");

  await expect(page.locator(".v41-compact-audit")).not.toHaveAttribute("open", "");
  await expect(page.locator(".v41-semantic-audit")).not.toHaveAttribute("open", "");
  await expect(page.locator(".v41-factor-audit")).not.toHaveAttribute("open", "");
  const diagnosis = page.locator(".v41-evaluation-diagnosis[data-diagnosis-status]");
  await expect(diagnosis).toBeVisible();
  await expect(diagnosis).toContainText("首要阻断 / 结论尚无权威评估结论");
  await expect(diagnosis).toContainText("缺失明细当前没有足够的候选轨道证据定位原因");
  await expect(diagnosis).toContainText("下一步查看已注册档位与只读技术证据");
  await expect(page.locator(".v41-factor-checklist > header")).toBeVisible();
});

test("V41 uses diagnosis as the only unassessed conclusion and explains stale market movement", async ({ page }) => {
  const payload = workspace();
  const focused = payload.matches.find((item) => item.fixture_id === payload.selected_fixture_id)!;
  focused.intelligence_state = "DATA_INCOMPLETE";
  focused.readiness.missing_fields = ["lineups", "ratings", "team_value"];
  focused.factual_summary = "错误的旧数据链结论";
  focused.evaluation_execution.diagnosis = {
    status: "CHECKPOINT_NOT_DUE",
    primary_blocker_zh: "第一个评估档位尚未到达",
    missing_detail_zh: "候选轨道尚未启动；尚未发生门禁判定。",
    next_step_zh: "等待最近一个已注册评估档位。",
    next_checkpoint: "T3_ODDS",
    next_checkpoint_at: "2026-08-09T15:45:00Z",
    non_blocking_missing_zh: ["阵容", "评级", "球队身价"],
    evidence_codes: ["T3_ODDS:PLANNED"],
  };
  const handicap = focused.market_radar.markets.ASIAN_HANDICAP;
  handicap.main_line = "0.25";
  handicap.prices = { HOME: 1.70, AWAY: 2.02 };
  handicap.quote_age_seconds = 22_740;
  handicap.movement = {
    status: "PRICE_MOVEMENT",
    from_captured_at: "2026-08-19T23:08:41Z",
    to_captured_at: "2026-08-20T23:01:20Z",
    line_delta: "0",
    price_delta: { HOME: 0.02, AWAY: 0.51 },
    probability_delta: { HOME: 0.064689, AWAY: -0.064689 },
  };
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");

  const row = page.locator(`.v41-shortlist-list [data-fixture-id='${focused.fixture_id}']`);
  await expect(row.locator(".v41-shortlist-title")).toContainText("本菲卡 vs 波尔图");
  await expect(row.locator(".v41-shortlist-title time")).toHaveText("22:30");
  await expect(row).toContainText("让球 -0.25 未变");
  await expect(row).toContainText("客赔 1.51 → 2.02（+33.8%）");
  await expect(row).toContainText("历史变化 · 当前不可执行");
  await expect(row).toContainText("当前报价已过期，等待 T3 更新");
  await expect(row.locator(".v41-stripe")).toHaveCount(1);
  await expect(row).toHaveCSS("border-left-width", "0px");

  const conclusionNodes = [
    row.locator(".v41-shortlist-status[data-primary-conclusion]"),
    page.locator(".v41-focus-summary[data-primary-conclusion]"),
    page.locator(".v41-evaluation-diagnosis[data-primary-conclusion]"),
  ];
  const conclusions = await Promise.all(conclusionNodes.map(async (node) => {
    await expect(node).toHaveCount(1);
    return node.getAttribute("data-primary-conclusion");
  }));
  expect(new Set(conclusions)).toEqual(new Set(["第一个评估档位尚未到达"]));
  await expect(page.locator(".v41-focus-summary")).toContainText("第一个评估档位尚未到达");
  await expect(page.locator(".v41-focus-summary")).not.toContainText("错误的旧数据链结论");
});

test("V41 makes the final official candidate card authoritative and folds repeated semantics", async ({ page }) => {
  const payload = workspace();
  const focused = payload.matches.find((item) => item.fixture_id === payload.selected_fixture_id)!;
  focused.evaluation_execution = {
    status: "CANDIDATE",
    ever_formed_candidate: true,
    final_states: [],
    latest_candidates: [{ market: "ASIAN_HANDICAP", selection: "AWAY", exact_line: "-0.5", decimal_odds: 1.88, bookmaker_id: "bookmaker-1", captured_at: "2026-08-09T15:15:00Z", evaluated_at: "2026-08-09T15:16:00Z", checkpoint: "T15_ODDS", final_state: "EVALUATED_CANDIDATE", final_active: true, later_unassessed_checkpoints: [] }],
    checkpoint_count: 2,
    market_evaluation_count: 2,
    checkpoints: ["T3_ODDS", "T15_ODDS"],
    markets: ["ASIAN_HANDICAP"],
    summary_zh: "已评估 2 次（T-3h / T-15m），最终官方状态仍为候选。",
    diagnosis: { status: "CANDIDATE_ACTIVE", primary_blocker_zh: "最终仍为候选", missing_detail_zh: "候选轨道已完成评估并保持有效。", next_step_zh: "等待赛果进入既有结算流程。", next_checkpoint: null, next_checkpoint_at: null, non_blocking_missing_zh: [], evidence_codes: [] },
  };
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");

  const official = page.locator(".v41-candidate--official");
  await expect(official.locator("header")).toContainText("检查点漏斗候选最终仍有效");
  await expect(official.locator("header")).not.toContainText("产品权限未启用");
  await expect(official).toContainText("让球主盘 · 盘口 -0.5 · 推荐客队 @1.88");
  await expect(official.locator("footer")).toHaveText(focused.evaluation_execution.summary_zh);
  await expect(page.locator(".v41-evaluation-diagnosis[data-diagnosis-status]")).toHaveCount(0);
  await expect(page.locator(".v41-semantic-audit")).not.toHaveAttribute("open", "");
});

test("V41 reads global capability state and distinguishes disabled from not implemented", async ({ page }) => {
  const payload = workspace();
  payload.runtime.recommendation_capabilities.formal_ah.feature_enabled = true;
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");

  const capabilities = page.locator(".v41-capabilities");
  await expect(capabilities).toContainText("分析选择：让球 开 / 大小球 开");
  await expect(capabilities).toContainText("影子候选 开");
  await expect(capabilities).toContainText("正式推荐：让球 开 / 大小球 未实现");
  await expect(capabilities).toContainText("实盘 关");
  await expect(page.locator(".v41-focus-meaning")).not.toContainText("产品权限未启用");
});

test("V41 uses one lifecycle decision for a match that never formed a candidate", async ({ page }) => {
  const payload = workspace();
  const focused = payload.matches.find((item) => item.fixture_id === payload.selected_fixture_id)!;
  focused.status = "FT";
  focused.outcome.is_finished = true;
  focused.evaluation_execution.status = "NO_CANDIDATE_FORMED";
  focused.evaluation_execution.ever_formed_candidate = false;
  focused.evaluation_execution.summary_zh = "本场未形成候选；期间有检查点错过，但不影响该结论。";
  focused.factual_summary = focused.evaluation_execution.summary_zh;
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");

  await expect(page.locator(`.v41-shortlist-list [data-fixture-id='${focused.fixture_id}']`)).toContainText("已完场 · 未形成候选");
  await expect(page.locator(".v41-focus-summary")).toContainText(focused.evaluation_execution.summary_zh);
  await expect(page.locator(".v41-focus")).not.toContainText("曾形成候选");
});

test("R5 factor checklist keeps model and shadow tracks separate per market", async ({ page }, testInfo) => {
  await installWorkspace(page, "stale");
  await page.goto("/");
  const checklist = page.locator(".v41-factor-checklist");
  await expect(checklist).toContainText("本场可进入模型预测账本；不能形成影子候选");
  await expect(checklist.locator(".v41-factor-tracks")).toContainText("模型账本 READY");
  await expect(checklist.locator(".v41-factor-tracks")).toContainText("候选因子投影 BLOCKED");
  await expect(checklist.locator(".v41-factor-row").filter({ hasText: "报价时效" })).toHaveCount(2);
  await expect(checklist).toContainText("让球主盘");
  await expect(checklist).toContainText("大小球主盘");
  await checklist.screenshot({ animations: "disabled", path: testInfo.outputPath("r5-factor-checklist.png") });
});

test("R6 distinguishes mainline identity from candidate quote lock", async ({ page }) => {
  await installWorkspace(page, "stale");
  await page.goto("/");
  const checklist = page.locator(".v41-factor-checklist");

  await expect(checklist).toContainText("模型账本 READY");
  await expect(checklist).toContainText("候选因子投影 BLOCKED");
  await expect(checklist).toContainText("主盘身份可解析 ≠ 候选报价可锁定");
  await expect(checklist.getByText("主盘身份可解析", { exact: true })).toHaveCount(2);
  await expect(page.getByText("报价锁定", { exact: true })).toHaveCount(1);
  await expect(page.locator(".v41-market-details__row")).toHaveCount(2);
  await expect(checklist).toContainText("模型预测账本事实");
  await expect(checklist).toContainText("尚未冻结");
});

test("R6 renders the complete persisted capture fact independently of current projection", async ({ page }) => {
  const payload = workspace();
  const selected = payload.matches.find((item) => item.fixture_id === payload.selected_fixture_id)!;
  selected.factor_checklist.conclusion_zh = "本场模型预测已冻结，等待真实完场结算；当前因子投影仅供对照：本场不可进入模型预测账本 —— 卡在 四字段 xG";
  selected.factor_checklist.ledger_fact = {
    state: "CAPTURED",
    capture_identity_hash: "a59386fc85e4a3e6f251948e1dc58e89719c0e00ea3a83f3b622c1ca9d4aa5cc",
    captured_at: "2026-08-09T13:00:00Z",
    model_family: "EXACT_DC_POISSON",
    model_version: "w2.formal.exact_dc_poisson.v1",
    calibration_version: "w2.formal.lambda_baseline_prior.v1",
    calibration_status: "BASELINE_PRIOR",
  };
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");

  const checklist = page.locator(".v41-factor-checklist");
  await expect(checklist).toContainText("本场模型预测已冻结，等待真实完场结算");
  await expect(checklist.locator(".v41-factor-ledger")).toContainText("capture a59386fc");
  await expect(checklist.locator(".v41-factor-ledger")).toContainText("开球前 1 小时 30 分");
  await expect(checklist.locator(".v41-factor-ledger")).toContainText("w2.formal.lambda_baseline_prior.v1 · BASELINE_PRIOR");
  await expect(checklist.locator(".v41-factor-ledger")).toContainText("结算状态：等待真实完场");
});

test("V41 keeps the zero-observation market state explicit", async ({ page }, testInfo) => {
  const payload = workspace();
  payload.selected_fixture_id = "1571808";
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");

  const focus = page.locator(".v41-focus");
  await expect(focus).toHaveAttribute("data-fixture-id", "1571808");
  await expect(focus.getByText("0 个真实快照", { exact: false })).toHaveCount(2);
  await expect(focus.getByText("暂无已落盘时间线证据，不推断走势。", { exact: true })).toHaveCount(2);
  await focus.screenshot({ animations: "disabled", path: testInfo.outputPath("actual-market-evidence-zero.png") });
});

test("one match projection failure remains visible without hiding the selected day", async ({ page }) => {
  const payload = workspace();
  const source = payload.matches[0] as WorkspaceMatch;
  const failed: WorkspaceMatchProjectionError = {
    projection_status: "ERROR",
    fixture_id: source.fixture_id,
    competition_id: source.competition_id,
    competition_name: source.competition_name,
    kickoff_utc: source.kickoff_utc,
    home_team_name: source.home_team_name,
    away_team_name: source.away_team_name,
    home_team_label: source.home_team_label,
    away_team_label: source.away_team_label,
    public_semantics: { scope: "MATCH", cause: "UNAVAILABLE" },
    status: source.status,
    outcome: source.outcome,
    projection_error: {
      code: "MATCH_PROJECTION_CONTRACT_VIOLATION",
      message: "该场投影未通过一致性校验，其余比赛不受影响",
      detail: "contract mismatch",
    },
  };
  payload.matches[0] = failed;
  payload.selected_fixture_id = failed.fixture_id;
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));

  await page.goto("/");

  await expect(page.locator("[data-fixture-id]")).toHaveCount(4);
  await expect(page.locator(".v41-shortlist")).toContainText("投影异常 · 1 场");
  await expect(page.locator(".v41-focus")).toContainText("单场投影已隔离");
  await expect(page.locator(".v41-focus")).toContainText("其余比赛不受影响");
});

test("V41 scoreline is exact 10,000 existing simulations with unconditional probability and sample count", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  const scoreline = page.locator(".v41-scoreline");
  await expect(scoreline).toContainText("10,000 次既有模拟");
  await expect(scoreline).toContainText("12.6%");
  await expect(scoreline).toContainText("样本 1260");
  await expect(scoreline).toContainText("不在读取时重新模拟");
});

test("V41 keeps dimension-specific risks, read isolation and forbidden semantics", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  const risks = page.locator(".v41-risk-list");
  await expect(risks).toContainText("大小球走势只有一个已落盘时间快照");
  await expect(risks).toContainText("大小球 2.5 模型落在市场观测区间外");
  await page.locator("#system-status > summary").click();
  await page.locator("#system-status > details > summary").click();
  await expect(page.locator("#system-status")).toContainText("provider_calls=0");
  await expect(page.locator("#system-status")).toContainText("db_writes=0");
  await expect(page.locator("#system-status")).toContainText("no_call_on_read=true");
  const body = page.locator("body");
  for (const forbidden of ["ROI", "CLV", "expected_value", "opportunity_score", "Boss Decision Console"]) await expect(body).not.toContainText(forbidden);
});

test("D16 keeps canonical risk codes in technical detail, not public explanations", async ({ page }) => {
  const payload = workspace("deployed");
  const focused = payload.matches.find((item) => item.fixture_id === "1571806")!;
  focused.risks.DATA_RISK = { dimension: "DATA_RISK", status: "INCIDENT", reason_codes: ["DATA_FIELD_STALE", "DATA_IDENTITY_NOT_READY"], explanation: "数据字段已超过新鲜度边界；比赛或盘口身份尚未完成" };
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");
  const risks = page.locator(".v41-risk-list");
  const publicCopy = risks.locator(".is-incident").first().locator(":scope > small");
  await expect(publicCopy).toContainText("数据字段已超过新鲜度边界");
  await expect(publicCopy).not.toContainText("DATA IDENTITY NOT READY");
  await expect(publicCopy).not.toContainText("DATA_IDENTITY_NOT_READY");
  await page.locator(".v41-compact-audit > summary").click();
  await risks.locator("details summary").first().click();
  await expect(risks).toContainText("DATA_IDENTITY_NOT_READY");
});

for (const [status, timestamp, copy] of [
  ["AVAILABLE", "2026-08-09T12:00:00Z", "仅展示当前有效验证证据"],
  ["STALE", "2026-08-08T12:00:00Z", "已过期（截至"],
  ["INCOMPLETE", "2026-08-09T12:00:00Z", "历史指标不完整（截至"],
  ["NOT_AVAILABLE", null, "尚无可用模型质量证据"],
] as const) {
  test(`D16 global quality ${status} is coherent`, async ({ page }) => {
    const payload = workspace();
    payload.global_model_quality.status = status;
    payload.global_model_quality.checkpoint_generated_at = timestamp;
    if (status !== "AVAILABLE") {
      payload.global_model_quality.model_log_loss = null;
      payload.global_model_quality.market_log_loss = null;
      payload.global_model_quality.model_brier = null;
      payload.global_model_quality.market_brier = null;
      payload.global_model_quality.model_calibration_error = null;
      payload.global_model_quality.sample_count = 0;
    }
    await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
    await page.goto("/");
    await expect(page.locator(".v41-quality")).toContainText(copy);
    if (status !== "AVAILABLE") await expect(page.locator(".v41-quality > div")).toHaveCount(0);
    if (status === "NOT_AVAILABLE") await expect(page.locator(".v41-quality")).not.toContainText("截至");
  });
}

test("V41 limited day keeps affected match names, kickoff times and recorded evaluation visible", async ({ page }) => {
  await installWorkspace(page, "limited");
  await page.goto("/");
  const shortlist = page.locator(".v41-shortlist");
  await expect(shortlist).toContainText("皇家马德里 vs 贝蒂斯");
  await expect(shortlist).toContainText("拜仁慕尼黑 vs 多特蒙德");
  await expect(shortlist.locator(".v41-limited-match")).toHaveCount(2);
  await expect(page.locator(".v41-today-primary")).toContainText("2场今日比赛");
  await expect(page.locator(".v41-today-primary")).toContainText("2 场可查看赛程");
  await expect(page.locator(".v41-today-primary")).toContainText("0 场可进行市场分析");
  await expect(page.locator(".v41-shortlist")).toContainText("盘口证据待采集 · 2 场");
  await expect(page.locator(".v41-shortlist")).not.toContainText("仅赛程");
  await expect(page.locator(".v41-focus")).toContainText("只展示已持久化事实，不用缺失数据补算");
  await expect(page.locator(".v41-focus")).not.toContainText("当日市场采集阻塞");
  await expect(page.locator(".v41-focus")).not.toContainText("等待既有调度");
  await expect(page.locator(".v41-global-stats")).toContainText("2026-08-09 22:49");
  await expect(page.locator(".v41-global-stats")).toContainText("约 1 小时 42 分后");
  await expect(page.getByText("COLLECTION_PROVIDER_EMPTY", { exact: true })).not.toBeVisible();
});

test("V41 limited day does not promise a schedule when none exists", async ({ page }) => {
  const payload = workspace("limited");
  payload.global_focus!.next_eval_at = null;
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");
  await expect(page.locator(".v41-global-stats")).toContainText("暂无适用于所选比赛日的调度记录");
  await expect(page.locator(".v41-focus")).not.toContainText("等待既有调度");
});

test("V41 match browser exposes all fixtures in priority order and one filter per present league", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await installWorkspace(page, "browser");
  await page.goto("/");
  const shortlist = page.locator(".v41-shortlist");
  const list = shortlist.locator(".v41-shortlist-list");
  const filters = shortlist.getByRole("toolbar", { name: "按联赛筛选比赛" });
  await expect(list.locator("button[data-fixture-id]")).toHaveCount(11);
  await expect(filters.getByRole("button")).toHaveCount(8);
  await expect(list.locator("button[data-fixture-id]").first()).toHaveAttribute("data-fixture-id", "browser-1");
  await expect(list.locator("button[data-fixture-id]").nth(1)).toHaveAttribute("data-fixture-id", "browser-0");
  await expect(list.locator(".v41-shortlist-title").first()).toHaveCSS("display", "flex");
  const rowHeights = await list.locator("button[data-fixture-id]").evaluateAll((items) => items.map((item) => item.getBoundingClientRect().height));
  expect(new Set(rowHeights).size).toBe(1);
  await expect(list.locator(".v41-shortlist-title strong").first()).toHaveCSS("white-space", "nowrap");
  await expect(list.locator(".v41-shortlist-title").first()).toHaveAttribute("title", / vs /);
  await expect(list.locator("button[data-fixture-id]").first()).toContainText("优先 1");
  const scroll = await list.evaluate((element) => ({ clientHeight: element.clientHeight, scrollHeight: element.scrollHeight, overflowY: getComputedStyle(element).overflowY }));
  expect(scroll.overflowY).toBe("auto");
  expect(scroll.scrollHeight).toBeGreaterThan(scroll.clientHeight);
  const panelBottoms = await page.evaluate(() => {
    const shortlistBounds = document.querySelector(".v41-shortlist")!.getBoundingClientRect();
    const listBounds = document.querySelector(".v41-shortlist-list")!.getBoundingClientRect();
    const focusBounds = document.querySelector(".v41-focus")!.getBoundingClientRect();
    return { shortlist: shortlistBounds.bottom, list: listBounds.bottom, focus: focusBounds.bottom };
  });
  expect(Math.abs(panelBottoms.shortlist - panelBottoms.focus)).toBeLessThanOrEqual(1);
  expect(Math.abs(panelBottoms.list - panelBottoms.focus)).toBeLessThanOrEqual(1);
  await shortlist.screenshot({ animations: "disabled", path: testInfo.outputPath("match-browser-all-top.png") });
  await list.evaluate((element) => { element.scrollTop = element.scrollHeight; });
  await shortlist.screenshot({ animations: "disabled", path: testInfo.outputPath("match-browser-all-bottom.png") });
  await filters.getByRole("button", { name: "Browser League 4 1" }).click();
  await expect(list.locator("button[data-fixture-id]")).toHaveCount(1);
  await expect(shortlist.locator(":scope > header")).toContainText("0 场优先 · 1 场可滚动查看");
  await expect(page.locator(".v41-focus")).toHaveAttribute("data-fixture-id", "browser-4");
});

test("V41 match browser hides the redundant filter for one present league", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  await expect(page.getByRole("toolbar", { name: "按联赛筛选比赛" })).toHaveCount(0);
});

test("V41 derives age across timezone and day boundaries and never labels a past evaluation as next", async ({ page }) => {
  const payload = workspace();
  payload.generated_at = "2026-08-10T00:30:00+08:00";
  const focused = payload.matches.find((item) => item.fixture_id === payload.selected_fixture_id)!;
  focused.market_radar.markets.ASIAN_HANDICAP.latest_snapshot_at = "2026-08-09T15:18:00Z";
  focused.market_radar.markets.ASIAN_HANDICAP.quote_age_seconds = 4320;
  focused.market_radar.markets.ASIAN_HANDICAP.timeline_points.at(-1)!.checkpoint = null;
  focused.market_collection = { latest_snapshot_at: "2026-08-09T15:18:00Z", latest_snapshot_checkpoint: "T24_OPEN_ODDS", target_checkpoint: "T12_OPEN_ODDS", scheduled_at: "2026-08-09T18:30:00Z", window_end_at: "2026-08-09T18:40:00Z", overdue: false, public_semantics: { scope: "MATCH", cause: "NOT_YET_DUE" } };
  focused.readiness.next_eval_at = "2026-08-09T16:30:00Z";
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");
  const freshness = page.locator("[data-market-details='ASIAN_HANDICAP']");
  await expect(freshness.locator("span").nth(1)).toHaveText("T24_OPEN_ODDS");
  const quoteAge = page.locator("[data-market='ASIAN_HANDICAP'] [data-quote-age-state='warning']");
  await expect(quoteAge.locator("span")).toHaveText("快照年龄");
  await expect(quoteAge.locator("strong")).toContainText("1 小时 12 分");
  await expect(freshness).toHaveCSS("display", "grid");
  await expect(page.locator(".v41-market-details .v41-market-technical")).toContainText("技术说明");
  const schedule = page.locator(".v41-next");
  await expect(schedule.locator("span").nth(2)).toHaveText("采集状态");
  await expect(schedule.locator("strong").nth(2)).toHaveText("未到 T12_OPEN_ODDS 采集时点");
  await expect(schedule.locator("span").nth(3)).toHaveText("计划时刻");
  await expect(schedule.locator("strong").nth(3)).toHaveText("2026-08-10 02:30（约 2 小时 0 分后）");
  await expect(schedule.locator("span").nth(4)).toHaveText("宽限结束");
  await expect(schedule.locator("strong").nth(4)).toHaveText("2026-08-10 02:40");
  await expect(schedule.locator("span").nth(5)).toHaveText("下次评估");
  await expect(schedule.locator("strong").nth(5)).toHaveText("评估时间已过期");
  await expect(schedule).toHaveCSS("display", "grid");
});

test("V41 shares market evidence labels across both markets", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  const details = page.locator(".v41-market-details");
  await expect(details.locator(".v41-market-details__head").getByText("市场证据", { exact: true })).toHaveCount(1);
  await expect(details.locator(".v41-market-details__head").getByText("快照档位", { exact: true })).toHaveCount(1);
  await expect(details.locator(".v41-market-details__head").getByText("走势证据", { exact: true })).toHaveCount(1);
  await expect(details.locator(".v41-market-details__head").getByText("报价锁定", { exact: true })).toHaveCount(1);
  await expect(details.locator(".v41-market-details__head").getByText("可用模型", { exact: true })).toHaveCount(1);
  await expect(details.locator(".v41-market-details__row")).toHaveCount(2);
  await expect(page.getByText("仅绘制已落盘快照", { exact: false })).toHaveCount(1);
  await expect(page.getByText("点间不插值、不推断缺失路径", { exact: false })).toHaveCount(1);
});

test("V41 finished match freezes quote age at kickoff and closes prematch planning", async ({ page }) => {
  const payload = workspace();
  payload.generated_at = "2026-08-10T20:00:00Z";
  const focused = payload.matches.find((item) => item.fixture_id === payload.selected_fixture_id)!;
  focused.status = "FT";
  focused.outcome.is_finished = true;
  focused.kickoff_utc = "2026-08-10T10:00:00Z";
  focused.market_radar.markets.ASIAN_HANDICAP.latest_snapshot_at = "2026-08-10T09:50:00Z";
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");

  const market = page.locator("[data-market='ASIAN_HANDICAP']");
  await expect(market).toContainText("开球前最后快照");
  await expect(market.locator(".v41-market-summary")).toContainText("报价年龄10 分钟");
  await expect(page.locator(".v41-next")).toContainText("采集状态赛前流程已关闭");
  await expect(page.locator(".v41-next")).toContainText("下次评估赛前流程已结束");
  await expect(page.locator("#factor-checklist-title")).toContainText("赛前未形成检查点漏斗评估");
  await expect(page.locator("#factor-checklist-title")).not.toContainText("尚未评估");
});

test("V41 keeps not-yet-due lineups out of anomalous missing inputs", async ({ page }) => {
  const payload = workspace();
  payload.generated_at = "2026-08-09T00:30:00Z";
  const focused = payload.matches.find((item) => item.fixture_id === payload.selected_fixture_id)!;
  focused.readiness.missing_fields = ["lineups", "xg", "ratings", "team_value"];
  focused.risks.DATA_RISK = {
    dimension: "DATA_RISK",
    status: "INCIDENT",
    reason_codes: ["DATA_REQUIRED_INPUT_MISSING", "DATA_STATUS_BLOCKED"],
    explanation: "待补齐：模型核心输入 xG、评级增强输入、球队身价增强输入；既有采集或模型投影形成后解除",
  };
  focused.lineup_collection = {
    target_checkpoint: "T60_ODDS_LINEUPS",
    scheduled_at: "2026-08-09T13:30:00Z",
    window_end_at: "2026-08-09T13:50:00Z",
    overdue: false,
    public_semantics: { scope: "MATCH", cause: "NOT_YET_DUE" },
  };
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");
  const risk = page.locator("[data-risk-axis='DATA_RISK']");
  await expect(risk).toContainText("待补齐：模型核心输入 xG、评级增强输入、球队身价增强输入");
  await expect(risk).not.toContainText("待补齐：首发");
  await expect(risk).toContainText("等待中：首发（T60_ODDS_LINEUPS 窗口）· 计划 2026-08-09 21:30（约 13 小时 0 分后）");
});

for (const state of [
  { overdue: false, expected: "T12_OPEN_ODDS 采集窗口进行中" },
  { overdue: true, expected: "T12_OPEN_ODDS 采集已逾期" },
] as const) {
  test(`V41 distinguishes collection grace from overdue failure: ${state.expected}`, async ({ page }) => {
    const payload = workspace();
    const focused = payload.matches.find((item) => item.fixture_id === payload.selected_fixture_id)!;
    focused.market_collection = {
      ...focused.market_collection,
      overdue: state.overdue,
      public_semantics: { scope: "MATCH", cause: "AWAITING_COLLECTION" },
    };
    await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
    await page.goto("/");
    await expect(page.locator(".v41-focus-summary b")).toHaveText("采集状态");
    await expect(page.locator(".v41-next strong").nth(2)).toHaveText(state.expected);
  });
}

test("V41 date navigation, Today, Refresh and keyboard focus are functional", async ({ page }) => {
  const requestedDates: string[] = [];
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => { requestedDates.push(new URL(route.request().url()).searchParams.get("date") || ""); return route.fulfill({ status: 200, json: workspace() }); });
  await page.goto("/");
  await page.getByLabel("选择比赛日").fill("2026-08-09");
  await expect.poll(() => requestedDates.at(-1)).toBe("2026-08-09");
  await page.getByRole("button", { name: "前一天" }).click();
  await expect.poll(() => requestedDates.at(-1)).toBe("2026-08-08");
  await page.getByLabel("选择比赛日").fill("2026-08-03");
  await expect.poll(() => requestedDates.at(-1)).toBe("2026-08-03");
  const requestsBeforeHistoryClick = requestedDates.length;
  const strip = page.getByRole("navigation", { name: "近七日比赛浏览" });
  await strip.getByRole("button", { name: "查看更早日期" }).click();
  await strip.getByRole("button").filter({ hasText: "2026-08-02" }).click();
  await expect.poll(() => requestedDates.at(-1)).toBe("2026-08-02");
  expect(requestedDates).toHaveLength(requestsBeforeHistoryClick + 1);
  await page.getByLabel("选择比赛日").focus();
  await page.keyboard.press("Tab");
  const focused = await page.evaluate(() => document.activeElement?.tagName);
  expect(["A", "BUTTON", "INPUT"]).toContain(focused);
  await expect(page.locator(":focus-visible")).toHaveCount(1);
});

test("refresh keeps the current workspace visible while the read is pending", async ({ page }, testInfo) => {
  let holdRefresh = false;
  let finishRefresh!: () => void;
  const refreshPending = new Promise<void>((resolve) => { finishRefresh = resolve; });
  await page.route("**/v1/dashboard/intelligence-workspace?**", async (route) => {
    if (holdRefresh) await refreshPending;
    await route.fulfill({ status: 200, json: workspace() });
  });
  await page.goto("/");
  await expect(page.locator(".dashboard-v41")).toBeVisible();
  holdRefresh = true;

  const refresh = page.getByRole("button", { name: "刷新" });
  await refresh.click();
  await expect(refresh).toBeDisabled();
  await expect(page.locator(".dashboard-v41")).toBeVisible();
  await page.screenshot({ animations: "disabled", path: testInfo.outputPath("actual-refresh-loading.png") });
  finishRefresh();
  await expect(refresh).toBeEnabled();
});

test("SC19 date strip exposes persisted counts and collection-window truth", async ({ page }) => {
  const payload = workspace();
  const selected = payload.date_strip.find((item) => item.football_day === payload.date)!;
  selected.market_evidence_fixture_count = 1;
  selected.market_collection_window_status = "MARKET_COLLECTION_DUE_EVIDENCE_NOT_READY";
  selected.public_semantics = { scope: "SELECTED_DAY", cause: "AWAITING_COLLECTION" };
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");

  const strip = page.getByRole("navigation", { name: "近七日比赛浏览" });
  await expect(strip.getByText("已持久化赛程", { exact: true })).toBeVisible();
  await expect(strip.getByText("1/13 联赛", { exact: false }).first()).toBeVisible();
  await expect(strip).toContainText("已落盘市场观察（含历史）1/3 场");
  await expect(strip.locator('[aria-current="date"] .v41-recent-days-title')).toHaveText("2026-08-09 · 3 场 · 今天");
  await expect(page.locator(".v41-today-primary")).toContainText("场尚无市场证据");
  await expect(page.locator(".v41-no-break")).toHaveCSS("white-space", "nowrap");
  await expect(strip).not.toContainText("市场证据可用");
  await expect(strip.getByText("W2 计划采集尚未开始", { exact: false }).first()).toBeVisible();
  await expect(strip).toContainText("每次只读取所选日期，不额外查询 Provider");
  await strip.getByRole("button", { name: "查看更晚日期" }).click();
  await expect(strip.getByText("2026-08-16", { exact: true })).toBeVisible();
});

test("mobile date strip keeps every status inside its own card", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installWorkspace(page);
  await page.goto("/");
  const strip = page.getByRole("navigation", { name: "近七日比赛浏览" });
  const statuses = strip.locator("button em");
  await expect(statuses).toHaveCount(7);
  const contained = await statuses.evaluateAll((items) => items.every((item) => {
    const card = item.closest("button")!.getBoundingClientRect();
    const status = item.getBoundingClientRect();
    return status.left >= card.left && status.right <= card.right
      && status.top >= card.top && status.bottom <= card.bottom
      && item.scrollWidth <= item.clientWidth && item.scrollHeight <= item.clientHeight;
  }));
  expect(contained).toBe(true);
  const selectedVisible = await strip.locator("[aria-current=date]").evaluate((item) => {
    const stripBounds = item.closest("nav")!.getBoundingClientRect();
    const itemBounds = item.getBoundingClientRect();
    return itemBounds.left >= stripBounds.left && itemBounds.right <= stripBounds.right;
  });
  expect(selectedVisible).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});

test("mobile selected date remains visible after the workspace replaces date-strip nodes", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-08-12T06:00:00Z"));
  await page.setViewportSize({ width: 390, height: 844 });
  const initial = workspace();
  initial.date = "2026-08-12";
  initial.date_strip = initial.date_strip.map((entry, index) => ({
    ...entry,
    football_day: new Date(Date.UTC(2026, 7, 5 + index)).toISOString().slice(0, 10),
  }));
  const selected = workspace();
  selected.date = "2026-08-14";
  selected.football_day_start_utc = "2026-08-14T04:00:00Z";
  selected.football_day_end_utc = "2026-08-15T04:00:00Z";
  selected.date_strip = selected.date_strip.map((entry, index) => ({
    ...entry,
    football_day: new Date(Date.UTC(2026, 7, 7 + index)).toISOString().slice(0, 10),
  }));
  await page.route("**/v1/dashboard/intelligence-workspace?**", async (route) => {
    const requestedDate = new URL(route.request().url()).searchParams.get("date");
    if (requestedDate === selected.date) {
      await new Promise((resolve) => setTimeout(resolve, 200));
      await route.fulfill({ status: 200, json: selected });
      return;
    }
    await route.fulfill({ status: 200, json: initial });
  });

  await page.goto("/");
  await page.getByLabel("选择比赛日").fill(selected.date);
  await expect(page.locator(".v41-today-day")).toContainText("比赛日 2026-08-14");
  const strip = page.getByRole("navigation", { name: "近七日比赛浏览" });
  const selectedVisible = await strip.locator("[aria-current=date]").evaluate((item) => {
    const stripBounds = item.closest("nav")!.getBoundingClientRect();
    const itemBounds = item.getBoundingClientRect();
    return itemBounds.left >= stripBounds.left && itemBounds.right <= stripBounds.right;
  });
  expect(selectedVisible).toBe(true);
});

test("V41 empty-day adjacent controls change the requested football day", async ({ page }) => {
  const requestedDates: string[] = [];
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => { requestedDates.push(new URL(route.request().url()).searchParams.get("date") || ""); return route.fulfill({ status: 200, json: workspace("empty") }); });
  await page.goto("/");
  await page.locator(".v41-adjacent-days button").first().click();
  await expect.poll(() => requestedDates.at(-1)).toBe("2026-08-08");
  await page.locator(".v41-adjacent-days button").last().click();
  await expect.poll(() => requestedDates.at(-1)).toBe("2026-08-10");
});

test("V41 exposes a prominent post-match validation center and hides raw codes in technical detail", async ({ page }) => {
  let requests = 0;
  const payload = workspace();
  payload.validation.forward_validation_records.outcomes = { settled_sample_count: 16 };
  payload.validation.forward_validation_records.eligible_count = 16;
  payload.validation.model_forecast.ever_formed_candidate_count = 5;
  payload.validation.model_forecast.final_candidate_count = 4;
  payload.validation.model_forecast.invalidated_candidate_count = 1;
  payload.validation.model_forecast.t30_evaluated_candidate_count = 3;
  payload.validation.model_forecast.t30_confirmed_candidate_count = 2;
  payload.validation.model_forecast.official_recommendations = [
    { evaluation_id: "eval-win", fixture_id: "official-win", evaluated_at: "2026-08-10T01:00:00Z", kickoff_utc: "2026-08-10T02:00:00Z", market: "ASIAN_HANDICAP", selection: "AWAY", exact_line: "1.0", decimal_odds: 1.87, home_team_label: payload.matches[0].home_team_label, away_team_label: payload.matches[0].away_team_label, score: "0-1", settlement: "WIN", profit_units: 0.87 },
    { evaluation_id: "eval-loss", fixture_id: "official-loss", evaluated_at: "2026-08-10T01:01:00Z", kickoff_utc: "2026-08-10T02:01:00Z", market: "TOTALS", selection: "UNDER", exact_line: "3.5", decimal_odds: 1.9, home_team_label: payload.matches[1].home_team_label, away_team_label: payload.matches[1].away_team_label, score: "3-1", settlement: "LOSS", profit_units: -1 },
    { evaluation_id: "eval-half-win", fixture_id: "official-half-win", evaluated_at: "2026-08-10T01:02:00Z", kickoff_utc: "2026-08-10T02:02:00Z", market: "ASIAN_HANDICAP", selection: "AWAY", exact_line: "0.25", decimal_odds: 1.77, home_team_label: payload.matches[2].home_team_label, away_team_label: payload.matches[2].away_team_label, score: "3-3", settlement: "HALF_WIN", profit_units: 0.385 },
    { evaluation_id: "eval-push", fixture_id: "official-push", evaluated_at: "2026-08-10T01:03:00Z", kickoff_utc: "2026-08-10T02:03:00Z", market: "TOTALS", selection: "UNDER", exact_line: "3.0", decimal_odds: 1.81, home_team_label: payload.matches[0].home_team_label, away_team_label: payload.matches[0].away_team_label, score: "1-2", settlement: "PUSH", profit_units: 0 },
  ];
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => { requests += 1; return route.fulfill({ status: 200, json: payload }); });
  await page.goto("/");
  const validation = page.locator("#secondary-validation");
  await expect(validation).toBeVisible();
  await expect(validation).toContainText("赛后验证");
  await expect(validation).toContainText("跨比赛日累计证据");
  await expect(validation.locator(".v41-validation-verdict")).toContainText("开赛前最后状态仍为候选且已结算 4 注，合计 +0.255 单位");
  await expect(validation.locator(".v41-validation-verdict")).toContainText("样本量远不足以判断模型好坏");
  await expect(validation.locator(".v41-validation-verdict")).not.toContainText("200");
  await expect(validation.locator(".v41-official-recommendations")).toContainText("曾形成候选5");
  await expect(validation.locator(".v41-official-recommendations")).toContainText("最终仍有效4");
  await expect(validation.locator(".v41-validation-t30")).toContainText("T-30 候选评估3");
  await expect(validation.locator(".v41-validation-t30")).toContainText("T-30 正式档位成功2");
  await expect(validation.getByText("模型预测验证账本", { exact: true })).not.toBeVisible();
  await expect(validation.getByText("历史已结算 ANALYSIS_PICK", { exact: true }).first()).not.toBeVisible();
  await expect(validation.getByText("当前流程逐门覆盖", { exact: false })).not.toBeVisible();
  await expect(validation.locator(".v41-validation-matches")).toBeVisible();
  await expect(validation.locator(".v41-official-recommendations b")).toHaveText(["赢", "输", "赢一半", "走盘"]);
  const recommendationRows = validation.locator(".v41-official-recommendations ol > li");
  await expect(recommendationRows).toHaveCount(4);
  await expect(recommendationRows.nth(0)).toHaveAttribute("data-settlement", "WIN");
  await expect(recommendationRows.nth(1)).toHaveAttribute("data-settlement", "LOSS");
  await expect(recommendationRows.nth(2)).toHaveAttribute("data-settlement", "HALF_WIN");
  await expect(recommendationRows.nth(3)).toHaveAttribute("data-settlement", "PUSH");
  for (const index of [0, 2]) {
    await expect(recommendationRows.nth(index).locator("b")).toHaveCSS("color", "rgb(208, 122, 111)");
    await expect(recommendationRows.nth(index).locator("em")).toHaveCSS("color", "rgb(208, 122, 111)");
  }
  for (const index of [1, 3]) {
    const colors = await recommendationRows.nth(index).locator("b, em").evaluateAll((nodes) =>
      nodes.map((node) => getComputedStyle(node).color),
    );
    expect(colors).not.toContain("rgb(208, 122, 111)");
  }
  const recommendationBeforeAudit = await validation.evaluate((node) => {
    const recommendation = node.querySelector(".v41-official-recommendations");
    const audit = node.querySelector(".v41-validation-audit--group");
    return Boolean(recommendation && audit && recommendation.compareDocumentPosition(audit) & Node.DOCUMENT_POSITION_FOLLOWING);
  });
  expect(recommendationBeforeAudit).toBe(true);
  await expect(validation).not.toContainText("有效输赢命中率");
  await validation.locator(".v41-validation-audit--group > summary").click();
  await expect(validation.getByText("历史遗留，非当前流程产出", { exact: false })).toBeVisible();
  await expect(validation.getByText("n=16、选择过程尚未审计", { exact: false })).toBeVisible();
  await expect(validation.getByText("已有 ≥3 场历史的球队")).toBeVisible();
  await expect(validation).toContainText("赛果基表记录36");
  await expect(validation).toContainText("不混入所选比赛日的前向记录与赛果缺口");
  await expect(validation).toContainText("赛果尚未产生");
  await expect(validation).not.toContainText("所选比赛日证据缺口");
  await expect(validation).not.toContainText("赛果尚未接入");
  await expect(validation.getByText("MISSING_OUTCOMES", { exact: true })).not.toBeVisible();
  const initialRequests = requests;
  await validation.locator(".v41-validation-technical summary").click();
  await expect(validation.getByText("FORWARD_RECORD", { exact: true })).toBeVisible();
  expect(requests).toBe(initialRequests);
});

test("official recommendation empty state is explicit", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  await expect(page.locator(".v41-official-recommendations")).toContainText("当日无检查点漏斗候选");
});

test("empty selected day never leaks replay gaps into public copy", async ({ page }) => {
  await installWorkspace(page, "empty");
  await page.goto("/");

  const validation = page.locator("#secondary-validation");
  await expect(validation).toContainText("所选比赛日没有比赛记录");
  await expect(validation).not.toContainText("所选比赛日证据缺口");
  await expect(validation).not.toContainText("赛果尚未接入");
  await expect(validation.getByText("MISSING_OUTCOMES", { exact: true })).not.toBeVisible();
  await expect(page.locator("#history > summary")).toHaveText("证据审计台 / 比赛记录");
  await expect(page.locator("#history > summary")).not.toContainText("回放");
});

test("finished selected-day records derive awaiting-outcome copy from public semantics", async ({ page }) => {
  const payload = workspace();
  for (const item of payload.matches) {
    item.status = "FT";
    item.outcome = { is_finished: true, is_tracked: true, is_recorded: false, public_semantics: { scope: "MATCH", cause: "AWAITING_COLLECTION" } };
  }
  payload.validation.history_replay.status = "MISSING_OUTCOMES";
  payload.validation.history_replay.replay_gaps = ["MISSING_OUTCOMES"];
  payload.validation.history_replay.outcome_tracking_summary = { tracked_fixture_ids: payload.matches.map((item) => item.fixture_id), matched_fixture_ids: [], missing_outcome_fixture_ids: payload.matches.map((item) => item.fixture_id), tracked_count: payload.matches.length, matched_outcome_count: 0, missing_outcome_count: payload.matches.length };
  payload.validation.history_replay.record_kind = "REPLAY";
  payload.validation.history_replay.public_semantics = { scope: "SELECTED_DAY", cause: "AWAITING_COLLECTION" };
  payload.date_strip[7].finished_fixture_count = payload.matches.length;
  payload.date_strip[7].upcoming_fixture_count = 0;
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");

  const validation = page.locator("#secondary-validation");
  await expect(validation).toContainText("赛果待采集");
  await expect(validation).toContainText("比赛已经结束，赛果仍待既有流程采集");
  await expect(validation).not.toContainText("赛果尚未产生");
  await expect(validation).not.toContainText("所选比赛日证据缺口");
  await expect(validation.getByText("MISSING_OUTCOMES", { exact: true }).first()).not.toBeVisible();
  await validation.locator(".v41-validation-technical summary").click();
  await expect(validation.getByText("MISSING_OUTCOMES", { exact: true }).first()).toBeVisible();
});

test("past-due upcoming records show status awaiting update, not outcome not yet due", async ({ page }) => {
  const payload = workspace();
  payload.generated_at = "2026-08-11T18:00:00Z";
  for (const item of payload.matches) {
    item.status = "UPCOMING";
    item.outcome = { is_finished: false, is_tracked: false, is_recorded: false, public_semantics: { scope: "MATCH", cause: "AWAITING_COLLECTION" } };
  }
  payload.validation.history_replay.status = "FORWARD_RECORD";
  payload.validation.history_replay.replay_gaps = [];
  payload.validation.history_replay.record_kind = "FORWARD_RECORD";
  payload.validation.history_replay.public_semantics = { scope: "SELECTED_DAY", cause: "AWAITING_COLLECTION" };
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");

  const validation = page.locator("#secondary-validation");
  await expect(validation.getByText("比赛状态待更新", { exact: true })).toHaveCount(3);
  await expect(validation).toContainText("计划开球时间已过，持久化比赛状态或赛果仍待既有流程更新");
  await expect(validation).not.toContainText("赛果尚未产生");
});

test("mixed selected-day records derive each outcome label from match semantics", async ({ page }) => {
  const payload = workspace();
  const awaiting = payload.matches.find((item) => item.fixture_id === "1571806")!;
  awaiting.status = "FT";
  awaiting.outcome = { is_finished: true, is_tracked: true, is_recorded: false, public_semantics: { scope: "MATCH", cause: "AWAITING_COLLECTION" } };
  const unassessed = payload.matches.find((item) => item.fixture_id === "1571808")!;
  unassessed.status = "FT";
  unassessed.outcome = { is_finished: true, is_tracked: false, is_recorded: false, public_semantics: { scope: "MATCH", cause: "UNASSESSED" } };
  payload.validation.history_replay.status = "MISSING_OUTCOMES";
  payload.validation.history_replay.replay_gaps = ["MISSING_OUTCOMES"];
  payload.validation.history_replay.outcome_tracking_summary = { tracked_fixture_ids: [awaiting.fixture_id, "1571807"], matched_fixture_ids: [], missing_outcome_fixture_ids: [awaiting.fixture_id], tracked_count: 2, matched_outcome_count: 0, missing_outcome_count: 1 };
  payload.validation.history_replay.record_kind = "MIXED_RECORD";
  payload.validation.history_replay.public_semantics = { scope: "SELECTED_DAY", cause: "AWAITING_COLLECTION" };
  payload.date_strip[7].finished_fixture_count = 2;
  payload.date_strip[7].upcoming_fixture_count = 1;
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");

  const rows = page.locator("#secondary-validation .v41-validation-matches li");
  await expect(rows.nth(0)).toContainText("赛果待采集");
  await expect(rows.nth(1)).toContainText("赛果尚未产生");
  await expect(rows.nth(2)).toContainText("赛果未纳入跟踪");
  await expect(page.locator("#secondary-validation")).toContainText(
    "已有 2 场完场；其余比赛状态或赛果仍待既有流程更新",
  );
  await expect(page.locator("#history > summary")).toHaveText("证据审计台 / 前向 / 回放记录");
});

test("recorded match outcomes render only the persisted outcome semantics", async ({ page }) => {
  const payload = workspace();
  for (const item of payload.matches) {
    item.status = "FT";
    item.outcome = { is_finished: true, is_tracked: true, is_recorded: true, public_semantics: { scope: "MATCH", cause: null } };
  }
  payload.validation.history_replay.status = "READY";
  payload.validation.history_replay.replay_gaps = [];
  payload.validation.history_replay.outcome_tracking_summary = { tracked_fixture_ids: payload.matches.map((item) => item.fixture_id), matched_fixture_ids: payload.matches.map((item) => item.fixture_id), missing_outcome_fixture_ids: [], tracked_count: payload.matches.length, matched_outcome_count: payload.matches.length, missing_outcome_count: 0 };
  payload.validation.history_replay.record_kind = "REPLAY";
  payload.validation.history_replay.public_semantics = { scope: "SELECTED_DAY", cause: null };
  payload.date_strip[7].finished_fixture_count = payload.matches.length;
  payload.date_strip[7].upcoming_fixture_count = 0;
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");

  const validation = page.locator("#secondary-validation");
  await expect(validation.locator(".v41-validation-matches").getByText("赛果已记录", { exact: true })).toHaveCount(3);
  await expect(validation).toContainText("3 场比赛的赛果已由既有流程记录");
});

test("V41 primary controls meet the bounded minimum target size", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  for (const selector of [".v41-date-nav button", ".v41-date-nav input", ".v41-recent-days button"]) {
    const box = await page.locator(selector).first().boundingBox();
    expect(box?.height, selector).toBeGreaterThanOrEqual(38);
  }
});

test("V41 1180 and 200% zoom preserve horizontal containment with a scrollable match browser", async ({ page }) => {
  await page.setViewportSize({ width: 1180, height: 1300 });
  await installWorkspace(page);
  await page.goto("/");
  await expect(page.locator(".v41-focus-body")).toBeVisible();
  const normal = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth, shortlist: getComputedStyle(document.querySelector(".v41-shortlist-list")!).overflowY, focus: getComputedStyle(document.querySelector(".v41-focus-body")!).overflowY }));
  expect(normal.scrollWidth).toBeLessThanOrEqual(normal.width);
  expect(normal.shortlist).toBe("auto");
  expect(normal.focus).toBe("visible");
  await page.setViewportSize({ width: 590, height: 650 });
  const zoomed = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth }));
  expect(zoomed.scrollWidth).toBeLessThanOrEqual(zoomed.width);
  await expect(page.getByRole("button", { name: "刷新" })).toBeVisible();
});

for (const viewport of [
  { width: 1280, height: 720 },
  { width: 1366, height: 768 },
  { width: 1512, height: 982 },
  { width: 1536, height: 1024 },
]) {
  test(`D16 ${viewport.width} keeps the focus in document flow and the match browser scrollable`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await installWorkspace(page, "deployed");
    await page.goto("/");
    await expect(page.locator(".v41-focus-body")).toBeVisible();
    const layout = await page.evaluate(() => ({
      width: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      focus: getComputedStyle(document.querySelector(".v41-focus-body")!).overflowY,
      shortlist: getComputedStyle(document.querySelector(".v41-shortlist-list")!).overflowY,
    }));
    expect(layout.scrollWidth).toBeLessThanOrEqual(layout.width);
    expect(layout.focus).toBe("visible");
    expect(layout.shortlist).toBe("auto");
  });
}

for (const viewport of [
  { width: 1366, height: 768, target: "d16-postdeploy-1366x768.png" },
  { width: 1512, height: 982, target: "d16-postdeploy-1512x982.png" },
]) {
  test(`D16 real-shape target image diff ${viewport.target}`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    await installWorkspace(page, "deployed");
    await page.goto("/");
    await expect(page.locator(".v41-focus-body")).toBeVisible();
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath(`actual-${viewport.target}`) });
    await expect(page).toHaveScreenshot(viewport.target, { animations: "disabled", maxDiffPixelRatio: .03 });
  });
}

function rgb(value: string): [number, number, number] {
  const parts = value.match(/[\d.]+/g)?.slice(0, 3).map(Number) || [0, 0, 0];
  return [parts[0], parts[1], parts[2]];
}

function luminance([r, g, b]: [number, number, number]): number {
  const linear = [r, g, b].map((channel) => { const value = channel / 255; return value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4; });
  return .2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2];
}

test("V41 representative normal text contrast is at least 4.5 to 1", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  for (const selector of [".v41-shortlist-copy strong", ".v41-focus-summary span", ".v41-diagnostic p", ".v41-global-grid strong"]) {
    if (!await page.locator(selector).count()) continue;
    const styles = await page.locator(selector).first().evaluate((element) => { const style = getComputedStyle(element); let parent = element.parentElement; while (parent && getComputedStyle(parent).backgroundColor === "rgba(0, 0, 0, 0)") parent = parent.parentElement; return { color: style.color, background: getComputedStyle(parent || document.body).backgroundColor }; });
    const foreground = luminance(rgb(styles.color));
    const background = luminance(rgb(styles.background));
    const ratio = (Math.max(foreground, background) + .05) / (Math.min(foreground, background) + .05);
    expect(ratio, selector).toBeGreaterThanOrEqual(4.5);
  }
});

for (const viewport of [
  { width: 1280, height: 720, target: "normal-1280x720.png" },
  { width: 1366, height: 768, target: "normal-1366x768.png" },
  { width: 1512, height: 982, target: "normal-1512x982.png" },
  { width: 1536, height: 1024, target: "normal-1536x1024.png" },
  { width: 1180, height: 1300, target: "normal-responsive-1180.png" },
]) {
  test(`V41 approved target image diff ${viewport.target}`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    await installWorkspace(page);
    await page.goto("/");
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath(`actual-${viewport.target}`) });
    await expect(page).toHaveScreenshot(viewport.target, { animations: "disabled", maxDiffPixelRatio: .2 });
  });
}

for (const scenario of ["limited", "calm", "stale", "empty"] as const) {
  test(`V41 approved state target image diff ${scenario}-1440x900.png`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await installWorkspace(page, scenario);
    await page.goto("/");
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath(`actual-${scenario}-1440x900.png`) });
    await expect(page).toHaveScreenshot(`${scenario}-1440x900.png`, { animations: "disabled", maxDiffPixelRatio: .2 });
  });
}

test("endpoint failure remains fail-closed without legacy fallback", async ({ page }) => {
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 503, json: { code: "SYSTEM_DEGRADED" } }));
  await page.goto("/");
  await expect(page.locator(".workspace-load-state--error")).toContainText("统一情报工作台暂不可用");
  await expect(page.locator(".workspace-load-state--error")).toContainText("不会回退旧 Dashboard，也不会填充合成数据");
});
