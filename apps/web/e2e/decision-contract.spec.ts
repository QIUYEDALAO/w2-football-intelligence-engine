import { expect, test, type Page } from "@playwright/test";
import type {
  IntelligenceWorkspace,
  WorkspaceMarket,
  WorkspaceMatch,
  WorkspaceRisks,
} from "../src/types/intelligenceWorkspace";

type Scenario = "normal" | "blocked" | "calm" | "stale" | "empty" | "deployed";

function risks(): WorkspaceRisks {
  return {
    EVENT_RISK: { dimension: "EVENT_RISK", status: "OK", reason_codes: [], explanation: "当前未见阵容、伤停或比赛事件风险证据。", assessment_status: "ASSESSED_CURRENT" },
    DATA_RISK: { dimension: "DATA_RISK", status: "ATTENTION", reason_codes: ["DATA_FIELD_STALE"], explanation: "大小球走势只有一个已落盘时间快照。", assessment_status: "ASSESSED_CURRENT" },
    MODEL_RISK: { dimension: "MODEL_RISK", status: "ATTENTION", reason_codes: ["MODEL_OUTSIDE_MARKET_RANGE"], explanation: "大小球 2.5 模型落在市场观测区间外。", assessment_status: "ASSESSED_CURRENT" },
    COLLECTION_RISK: { dimension: "COLLECTION_RISK", status: "OK", reason_codes: [], explanation: "当前持久化采集终态未见异常。", assessment_status: "ASSESSED_CURRENT", evidence_basis: "PERSISTED_TERMINAL_ASSESSMENT", source_as_of: "2026-08-09T13:00:00Z" },
  };
}

function market(name: "ASIAN_HANDICAP" | "TOTALS", count: number, stale = false): WorkspaceMarket {
  const handicap = name === "ASIAN_HANDICAP";
  const lines = handicap ? ["-0.50", "-0.50", "-0.75"] : ["2.50"];
  const sides = handicap ? ["HOME", "AWAY"] : ["OVER", "UNDER"];
  const points = Array.from({ length: count }, (_, index) => ({
    capture_id: `${name.toLowerCase()}-${index + 1}`,
    captured_at: `2026-08-09T${handicap ? ["06:02", "09:05", "12:11"][index] : "11:48"}:00Z`,
    canonical_line: lines[index] || lines.at(-1) || null,
    bookmaker_count: handicap ? 11 + index + (index > 0 ? 1 : 0) : 6,
    prices: { [sides[0]]: 1.93 + index / 100, [sides[1]]: 1.97 - index / 100 },
    probabilities: { [sides[0]]: 0.5, [sides[1]]: 0.5 },
  }));
  const status = !count ? "INSUFFICIENT" : stale ? "STALE" : "READY";
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
    freshness: { status: stale ? "STALE" : count ? "FRESH" : "NOT_AVAILABLE" },
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
    cross_sectional_comparison_status: stale ? "PAUSED_STALE" : count ? "AVAILABLE" : "INSUFFICIENT",
    latest_snapshot_at: points.at(-1)?.captured_at || null,
    freshness_max_age_seconds: 21_600,
  };
}

function match(id: string, options: { rich?: boolean; stale?: boolean; modelWarning?: boolean } = {}): WorkspaceMatch {
  const ah = market("ASIAN_HANDICAP", options.rich ? 3 : 0, options.stale);
  const totals = market("TOTALS", options.rich ? 1 : 0, options.stale);
  const reason = options.stale ? "STALE_MARKET_MEMORY" : options.modelWarning ? "MODEL_DIAGNOSTIC" : options.rich ? "MARKET_MOVEMENT" : null;
  const relationStatus = options.stale ? "MARKET_NOT_READY" : options.modelWarning ? "MODEL_OUTSIDE_MARKET_RANGE" : "COMPARABLE_WITHIN_MARKET_RANGE";
  const relation = (name: "ASIAN_HANDICAP" | "TOTALS") => ({ market: name, status: options.stale ? "MARKET_NOT_READY" : name === "TOTALS" && options.rich ? "MODEL_OUTSIDE_MARKET_RANGE" : relationStatus, canonical_line: name === "ASIAN_HANDICAP" ? "-0.75" : "2.50", bookmaker_count: name === "ASIAN_HANDICAP" ? 14 : 6, freshness_status: options.stale ? "STALE" : "FRESH", diagnostics: options.modelWarning || (name === "TOTALS" && options.rich) ? [{ status: "OUTSIDE_RANGE" }] : [], blockers: options.stale ? ["MARKET_STALE"] : [] });
  const teams: Record<string, [string, string]> = { "1571806": ["Benfica", "Porto"], "1571807": ["Real Madrid", "Real Betis"], "1571808": ["Bayern Munich", "Borussia Dortmund"] };
  const kickoff: Record<string, string> = { "1571806": "2026-08-09T14:30:00Z", "1571807": "2026-08-09T15:00:00Z", "1571808": "2026-08-09T15:30:00Z" };
  return {
    fixture_id: id,
    competition_id: "primeira_liga",
    competition_name: "Primeira Liga",
    kickoff_utc: kickoff[id] || "2026-08-09T14:30:00Z",
    home_team_name: teams[id]?.[0] || `Home ${id}`,
    away_team_name: teams[id]?.[1] || `Away ${id}`,
    status: "NS",
    intelligence_state: options.modelWarning ? "MODEL_DIAGNOSTIC_WARNING" : options.rich ? "MARKET_MOVEMENT" : "DATA_INCOMPLETE",
    intelligence_reason_codes: [options.stale ? "MARKET_STALE" : options.modelWarning ? "MODEL_OUTSIDE_MARKET_RANGE" : options.rich ? "MARKET_LINE_MOVEMENT" : "DATA_INCOMPLETE"],
    priority_reason_primary: reason,
    priority_reason_secondary: options.stale ? ["MARKET_MOVEMENT", "DATA_INCOMPLETE"] : options.rich && !options.modelWarning ? ["MODEL_DIAGNOSTIC"] : options.rich ? [] : ["DATA_INCOMPLETE"],
    factual_summary: options.stale ? "已落盘 AH/OU 历史市场证据已过期；当前走势与模型—市场比较暂停；等待既有调度形成新快照。" : options.rich ? "已有当前 AH/OU 持久化时间线；可展示已证实走势并进行模型—市场诊断；状态随既有调度形成的新证据更新。" : "尚无已落盘 AH/OU 市场证据；无法生成走势或当前模型—市场比较；等待既有调度形成证据。",
    risks: risks(),
    readiness: { status: options.rich && !options.stale ? "READY" : options.stale ? "STALE" : "BLOCKED", reason_code: options.stale ? "MARKET_STALE" : options.rich ? "EVIDENCE_READY" : "DATA_INCOMPLETE", reason_codes: [], missing_fields: options.rich ? [] : ["market"], stale_fields: options.stale ? ["market"] : [], action: "WAIT_FOR_NEXT_SCHEDULED_EVALUATION", next_eval_at: "2026-08-09T13:22:00Z", provider_budget_status: "PROTECTED", lineup_status: "AVAILABLE", lineup_expectation: "ADVISORY" },
    market_fact: { status: ah.status, source_status: ah.source_status, main_line: ah.main_line, current_odds: ah.prices, market_probabilities: ah.probabilities, price_reference: "LAST_AVAILABLE_PREMATCH_SNAPSHOT", canonical_close_status: "NOT_OBTAINABLE_FROM_CURRENT_PROVIDER" },
    w2_analysis: { status: "ANALYSIS_REFERENCE", proof_status: "NOT_PROVEN", decision_tier: "WATCH", analysis_state: relationStatus, reason_codes: [], model_view: { status: "READY", source_status: "READY", model_version: "w2-existing-v1", calibration_version: "cal-v1", calibration_status: "AVAILABLE", simulations_completed: 10_000 }, model_market_relation: { ASIAN_HANDICAP: relation("ASIAN_HANDICAP"), TOTALS: relation("TOTALS") } },
    formal_recommendation: { status: "OFF", reason: "PRODUCT_AUTHORITY_DISABLED" },
    market_radar: { schema_version: "w2.market-radar.v1", markets: { ASIAN_HANDICAP: ah, TOTALS: totals } },
    model_lab: { schema_version: "w2.model-lab.v1", w2_model: { status: "READY", source_status: "READY", model_version: "w2-existing-v1", calibration_status: "AVAILABLE" }, market: { ASIAN_HANDICAP: { status: ah.status, source_status: ah.source_status, main_line: ah.main_line, bookmaker_count: ah.bookmaker_count, freshness: ah.freshness }, TOTALS: { status: totals.status, source_status: totals.source_status, main_line: totals.main_line, bookmaker_count: totals.bookmaker_count, freshness: totals.freshness } }, api_football_prediction: { status: "NOT_AVAILABLE", role: "EXTERNAL_MODEL_BENCHMARK", reason_code: "API_FOOTBALL_PREDICTION_NOT_PROJECTED" }, relation: { ASIAN_HANDICAP: relation("ASIAN_HANDICAP"), TOTALS: relation("TOTALS") }, historical_validation: { final_verdict: "NO_EDGE", reexecuted: false } },
    scoreline_reference: options.rich && !options.stale ? { label: "MODEL_SCORELINE_REFERENCE", proof_status: "NOT_PROVEN", status: "READY", simulations_completed: 10_000, top3: [{ scoreline: "1-1", unconditional_probability: .126, sample_count: 1260 }, { scoreline: "2-1", unconditional_probability: .101, sample_count: 1010 }, { scoreline: "1-0", unconditional_probability: .094, sample_count: 940 }] } : { label: "MODEL_SCORELINE_REFERENCE", proof_status: "NOT_PROVEN", status: "UNAVAILABLE", simulations_completed: null, top3: [] },
    evidence: { card_hash: `card-${id}`, artifact_hash: `artifact-${id}`, source: "decision_contract", source_event_at: "2026-08-09T13:00:00Z", decision_role: "DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY" },
  };
}

function workspace(scenario: Scenario = "normal"): IntelligenceWorkspace {
  const rich = match("1571806", { rich: true, stale: scenario === "stale" });
  const other = [match("1571807", { rich: true }), match("1571808", { modelWarning: true })];
  const deployedMatches = [match("1571807"), match("1571806", { rich: true, stale: true }), match("1571808")];
  const matches = scenario === "deployed"
    ? deployedMatches
    : scenario === "normal" || scenario === "stale"
      ? [other[0], rich, other[1]]
      : scenario === "blocked"
        ? [match("1571807"), match("1571808")]
        : [];
  const mode = scenario === "blocked" ? "BLOCKED" : scenario === "calm" ? "CALM" : scenario === "empty" ? "EMPTY" : "NORMAL";
  const focusType = mode === "BLOCKED" ? "GLOBAL_INCIDENT" : mode === "CALM" ? "DAY_SUMMARY" : mode === "EMPTY" ? "EMPTY_STATE" : "MATCH";
  const focusId = mode === "NORMAL" ? "1571806" : null;
  const counts = mode === "NORMAL" ? scenario === "deployed" ? { STALE_MARKET_MEMORY: 1 } : scenario === "stale" ? { STALE_MARKET_MEMORY: 1, MARKET_MOVEMENT: 1, MODEL_DIAGNOSTIC: 1 } : { MARKET_MOVEMENT: 2, MODEL_DIAGNOSTIC: 1 } : {};
  const globalFocus = mode === "NORMAL" ? null : {
    status: mode === "BLOCKED" ? "INCIDENT" as const : mode === "CALM" ? "CALM" as const : "EMPTY" as const,
    reason_code: mode === "BLOCKED" ? "COLLECTION_PROVIDER_EMPTY" : mode === "CALM" ? "NO_PRIORITY_REVIEW_ITEMS" : "NO_FIXTURES_IN_FOOTBALL_DAY",
    factual_summary: mode === "BLOCKED" ? "当日市场采集未形成可解释证据。" : mode === "CALM" ? "当前没有达到优先复核条件的比赛。" : "本比赛日观察池内没有比赛；不会从其他日期填充。",
    affected_fixture_count: mode === "BLOCKED" ? matches.length : 0,
    affected_competition_count: mode === "BLOCKED" ? 1 : 0,
    source_as_of: "2026-08-09T13:05:00Z",
    next_eval_at: mode === "CALM" || mode === "BLOCKED" ? "2026-08-09T14:49:00Z" : null,
    recovery_condition: mode === "BLOCKED" ? "等待既有调度形成新的持久化市场快照；本页不调用 Provider。" : null,
  };
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
    day_mode: mode,
    default_focus_type: focusType,
    default_focus_fixture_id: focusId,
    selected_fixture_id: focusId,
    today_summary: { match_count: mode === "BLOCKED" ? matches.length : mode === "CALM" ? 9 : mode === "EMPTY" ? 0 : 26, competition_count: mode === "BLOCKED" ? 1 : mode === "CALM" ? 7 : mode === "EMPTY" ? 0 : 13, priority_match_count: Object.values(counts).reduce((sum, count) => sum + count, 0), priority_group_count: Object.keys(counts).length, primary_reason_counts: counts },
    global_focus: globalFocus,
    global_model_quality: { status: "AVAILABLE", checkpoint_key: "performance:cohort:all", checkpoint_generated_at: "2026-08-09T12:00:00Z", freshness_max_age_seconds: 86_400, model_log_loss: .512, market_log_loss: .508, model_brier: .178, market_brier: .174, model_calibration_error: .026, sample_count: 34 },
    read_contract: { provider_calls: 0, db_writes: 0, would_write_checkpoint: false, no_call_on_read: true },
    runtime: { product: "FOOTBALL_MARKET_INTELLIGENCE_PLUS_MODEL_DIAGNOSTICS", public_dashboard_authority: "NEW_INTELLIGENCE_WORKSPACE_ONLY", active_whitelist_count: 13, free_bridge_mode: "SHADOW_ONLY", market_price_attention_threshold_ratio: 0.02, candidate: "OFF", formal: "OFF", lock: "OFF", production: "OFF" },
    navigation: { current_date: "2026-08-09", previous_date: "2026-08-08", next_date: "2026-08-10", next_available_date: "2026-08-10" },
    attention: matches.map((item) => ({ fixture_id: item.fixture_id, kickoff_utc: item.kickoff_utc, intelligence_state: item.intelligence_state, reason_codes: item.intelligence_reason_codes, affected_domains: ["MARKET"], factual_summary: item.intelligence_reason_codes.join("；"), readiness_status: item.readiness.status, readiness_context: { reason_code: item.readiness.reason_code, missing_fields: item.readiness.missing_fields, stale_fields: item.readiness.stale_fields, action: item.readiness.action }, next_eval_at: item.readiness.next_eval_at, risks: item.risks })),
    matches,
    validation: { probability: { status: "AVAILABLE", sample_count: 34, model_brier: .178, market_brier: .174, model_minus_market_brier: .004, model_log_loss: .512, market_log_loss: .508, model_minus_market_log_loss: .004, model_calibration_error: .026, market_calibration_error: .021, model_reliability_bins: [], market_reliability_bins: [], checkpoint_metadata: { checkpoint_key: "performance:cohort:all" } }, directional: { status: "SAMPLE_BUILDING", source_status: "AVAILABLE", probability_evidence_ready: false, validation_n: 36, decisive_n: 34, correct: 18, wrong: 16, push: 1, void: 1, direction_accuracy: 18 / 34, effective_n: 34, market_direction_benchmark: "NOT_DEFINED", only_record_reason: "PROBABILITY_QUALITY_NOT_READY" }, league_performance: [], tournament_performance: [], forward_validation_records: { status: "AVAILABLE", validation_count: 36, eligible_count: 34, excluded_count: 2, excluded_share: 2 / 36, excluded_by_reason: { MARKET_IDENTITY_NOT_READY: 2 }, pending_count: 0, outcomes: {}, checkpoint_metadata: { checkpoint_key: "performance:cohort:all" } }, history_replay: { status: "AVAILABLE_WITH_GAPS", known_at: { has_day_view: true }, decision_summary: { total_cards: matches.length, lock_eligible_count: 0, by_decision_tier: { WATCH: matches.length }, by_data_status: { READY: matches.length } }, reason_summary: [], outcome_tracking_summary: {}, card_hash_checks: [], replay_gaps: ["MISSING_OUTCOMES"] } },
    external_intelligence: { weather: { status: "NOT_CONNECTED", affects_match_readiness: false }, news: { status: "NOT_CONNECTED", affects_match_readiness: false }, sentiment: { status: "NOT_CONNECTED", affects_match_readiness: false }, advanced_xg: { status: "NOT_CONNECTED", affects_match_readiness: false } },
    freshness: { domains: {} },
    data_operations: { read_model_source: "dashboard_read_model", checkpoint_key: "dashboard:day_view:2026-08-09", degradation: { state: mode === "BLOCKED" || scenario === "deployed" ? "BLOCKED_DAY" : mode === "EMPTY" ? "EMPTY_DAY" : "HEALTHY" }, counts: { total: matches.length }, system_health: mode === "BLOCKED" || scenario === "deployed" ? "BLOCKED_DAY" : "HEALTHY", public_system_health: mode === "BLOCKED" ? "DAY_BLOCKED" : scenario === "deployed" ? "PARTIAL_DEGRADATION" : "HEALTHY", provider_budget_status: "PROTECTED" },
  };
}

async function installWorkspace(page: Page, scenario: Scenario = "normal"): Promise<void> {
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: workspace(scenario) }));
}

test("V41 uses backend focus authority and never falls back to matches[0]", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  await expect(page.locator(".dashboard-v41")).toHaveAttribute("data-day-mode", "NORMAL");
  await expect(page.locator(".v41-focus")).toHaveAttribute("data-fixture-id", "1571806");
  await expect(page.locator(".v41-shortlist-list button").first()).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".v41-focus h1")).toContainText("本菲卡");
  await expect(page.locator(".v41-shortlist > header")).toContainText("赔率相对变化 ≥ 2%");
  await expect(page.getByLabel("选择比赛日")).toHaveValue(/^\d{4}-\d{2}-\d{2}$/);
  await expect(page.locator(".v41-today-day")).toContainText("比赛日 2026-08-09 12:00 → 2026-08-10 12:00（不含）");
});

test("V41 presents unassessed model evidence in Chinese and keeps codes technical", async ({ page }) => {
  const payload = workspace();
  const focused = payload.matches.find((item) => item.fixture_id === payload.default_focus_fixture_id)!;
  focused.w2_analysis.model_view.status = "PRIOR_ONLY";
  focused.model_lab.w2_model.status = "PRIOR_ONLY";
  for (const relation of Object.values(focused.w2_analysis.model_market_relation)) {
    relation.status = "MODEL_NOT_READY";
    relation.blockers = ["MODEL_CALIBRATION_NOT_READY"];
  }
  focused.risks.MODEL_RISK = {
    dimension: "MODEL_RISK",
    status: "ATTENTION",
    reason_codes: ["MODEL_SIMULATION_NOT_READY"],
    explanation: "尚无可用模型评估证据",
    assessment_status: "UNASSESSED",
  };
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");

  await expect(page.locator(".v41-three-layer")).toContainText("模型尚未就绪");
  await expect(page.locator(".v41-diagnostic")).toContainText("模型尚未就绪");
  await expect(page.locator(".v41-diagnostic")).not.toContainText("MODEL_NOT_READY");
  await expect(page.locator(".v41-risk-list")).toContainText("模型风险未评估尚无可用模型评估证据");
  await expect(page.getByText("MODEL_CALIBRATION_NOT_READY", { exact: true })).not.toBeVisible();
});

test("D16 deployed real shape keeps NORMAL authority, useful stale focus and auditable reasons", async ({ page }) => {
  await installWorkspace(page, "deployed");
  await page.goto("/");
  await expect(page.locator(".dashboard-v41")).toHaveAttribute("data-day-mode", "NORMAL");
  await expect(page.locator("[data-day-mode-label]")).toHaveText("正常日");
  await expect(page.locator("[data-public-system-health]")).toHaveText("系统数据部分降级");
  await expect(page.locator("header.v41-header")).not.toContainText("BLOCKED DAY");
  await expect(page.locator(".v41-focus")).toHaveAttribute("data-fixture-id", "1571806");
  await expect(page.locator(".v41-shortlist > header")).toContainText("1 场优先");
  await expect(page.locator(".v41-shortlist-list")).toContainText("主因：证据已过期");
  await expect(page.locator(".v41-shortlist-list")).toContainText("次因：盘口或赔率变化、数据不完整");
  await expect(page.locator(".v41-shortlist-list")).toContainText("其他关注 · 2 场（不计入优先）");
  await expect(page.locator(".v41-focus-summary")).toContainText("当前走势与模型—市场比较暂停");
});

for (const [scenario, mode, focus, copy] of [
  ["blocked", "BLOCKED", "GLOBAL_INCIDENT", "今日比赛可查看，市场分析暂无证据"],
  ["calm", "CALM", "DAY_SUMMARY", "今日未发现需优先排查的比赛"],
  ["empty", "EMPTY", "EMPTY_STATE", "本比赛日没有纳入观察池的比赛"],
] as const) {
  test(`V41 ${scenario} renders its exact non-match focus`, async ({ page }) => {
    await installWorkspace(page, scenario);
    await page.goto("/");
    await expect(page.locator(".dashboard-v41")).toHaveAttribute("data-day-mode", mode);
    await expect(page.locator(".v41-focus")).toHaveAttribute("data-focus-type", focus);
    await expect(page.locator(".v41-focus")).toContainText(copy);
    await expect(page.locator(".v41-focus")).not.toHaveAttribute("data-fixture-id", /.+/);
  });
}

test("V41 separates trend evidence from same-time comparison and preserves stale Market Memory", async ({ page }) => {
  await installWorkspace(page, "stale");
  await page.goto("/");
  const totals = page.locator("[data-market='TOTALS']");
  await expect(totals).toContainText("走势证据：证据不足");
  await expect(totals).toContainText("历史证据可见，当前比较暂停");
  await expect(page.locator(".v41-focus-summary")).toContainText("当前走势与模型—市场比较暂停");
  await expect(page.locator(".v41-scoreline")).toHaveCount(0);
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

test("V41 blocked day keeps affected match names, kickoff times and recorded evaluation visible", async ({ page }) => {
  await installWorkspace(page, "blocked");
  await page.goto("/");
  const shortlist = page.locator(".v41-shortlist");
  await expect(shortlist).toContainText("皇家马德里 vs 贝蒂斯");
  await expect(shortlist).toContainText("拜仁慕尼黑 vs 多特蒙德");
  await expect(shortlist.locator(".v41-blocked-match")).toHaveCount(2);
  await expect(page.locator(".v41-today-primary")).toContainText("2场今日比赛");
  await expect(page.locator(".v41-today-primary")).toContainText("2 场可查看赛程");
  await expect(page.locator(".v41-today-primary")).toContainText("0 场可进行市场分析");
  await expect(page.locator(".v41-shortlist")).toContainText("仅赛程比赛 · 2 场");
  await expect(page.locator(".v41-focus")).toContainText("市场证据尚未形成");
  await expect(page.locator(".v41-focus")).not.toContainText("当日市场采集阻塞");
  await expect(page.locator(".v41-focus")).not.toContainText("等待既有调度");
  await expect(page.locator(".v41-global-stats")).toContainText("2026-08-09 22:49");
  await expect(page.locator(".v41-global-stats")).toContainText("约 1 小时 42 分后");
  await expect(page.getByText("COLLECTION_PROVIDER_EMPTY", { exact: true })).not.toBeVisible();
});

test("V41 blocked day does not promise a schedule when none exists", async ({ page }) => {
  const payload = workspace("blocked");
  payload.global_focus!.next_eval_at = null;
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");
  await expect(page.locator(".v41-global-stats")).toContainText("暂无调度记录");
  await expect(page.locator(".v41-focus")).not.toContainText("等待既有调度");
});

test("V41 derives age across timezone and day boundaries and never labels a past evaluation as next", async ({ page }) => {
  const payload = workspace();
  payload.generated_at = "2026-08-10T00:30:00+08:00";
  const focused = payload.matches.find((item) => item.fixture_id === payload.default_focus_fixture_id)!;
  focused.market_radar.markets.ASIAN_HANDICAP.latest_snapshot_at = "2026-08-09T15:18:00Z";
  focused.readiness.next_eval_at = "2026-08-09T16:30:00Z";
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 200, json: payload }));
  await page.goto("/");
  await expect(page.locator("[data-market='ASIAN_HANDICAP']")).toContainText("距最新快照 1 小时 12 分");
  await expect(page.locator(".v41-next")).toContainText("评估时间已过期");
  await expect(page.locator(".v41-next")).not.toContainText("下次评估");
});

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
  await page.getByRole("button", { name: "2026-08-02 查看" }).click();
  await expect.poll(() => requestedDates.at(-1)).toBe("2026-08-02");
  expect(requestedDates).toHaveLength(requestsBeforeHistoryClick + 1);
  await page.keyboard.press("Tab");
  const focused = await page.evaluate(() => document.activeElement?.tagName);
  expect(["A", "BUTTON", "INPUT"]).toContain(focused);
  await expect(page.locator(":focus-visible")).toHaveCount(1);
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
  payload.validation.forward_validation_records.outcomes = { settled_sample_count: 20 };
  payload.validation.history_replay.outcome_tracking_summary = { matched_outcome_count: 20, missing_outcome_count: 3 };
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => { requests += 1; return route.fulfill({ status: 200, json: payload }); });
  await page.goto("/");
  const validation = page.locator("#secondary-validation");
  await expect(validation).toBeVisible();
  await expect(validation).toContainText("赛后验证");
  await expect(validation).toContainText("跨比赛日累计证据");
  await expect(validation).toContainText("验证总记录36");
  await expect(validation).toContainText("已结算20");
  await expect(validation).toContainText("赛果匹配 / 缺失20 / 3");
  await expect(validation).toContainText("当前证据缺口：赛果尚未接入");
  await expect(validation.getByText("MISSING_OUTCOMES", { exact: true })).not.toBeVisible();
  const initialRequests = requests;
  await validation.locator(".v41-validation-technical summary").click();
  await expect(validation.getByText("MISSING_OUTCOMES", { exact: true })).toBeVisible();
  expect(requests).toBe(initialRequests);
});

test("V41 primary controls meet the bounded minimum target size", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  for (const selector of [".v41-date-nav button", ".v41-date-nav input", ".v41-recent-days button"]) {
    const box = await page.locator(selector).first().boundingBox();
    expect(box?.height, selector).toBeGreaterThanOrEqual(38);
  }
});

test("V41 1180 and 200% zoom preserve natural flow without horizontal or nested primary scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 1180, height: 1300 });
  await installWorkspace(page);
  await page.goto("/");
  await expect(page.locator(".v41-focus-body")).toBeVisible();
  const normal = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth, shortlist: getComputedStyle(document.querySelector(".v41-shortlist-list")!).overflowY, focus: getComputedStyle(document.querySelector(".v41-focus-body")!).overflowY }));
  expect(normal.scrollWidth).toBeLessThanOrEqual(normal.width);
  expect(normal.shortlist).toBe("visible");
  expect(normal.focus).toBe("visible");
  await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
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
  test(`D16 ${viewport.width} has one vertical scroll path`, async ({ page }) => {
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
    expect(layout.shortlist).toBe("visible");
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

for (const scenario of ["blocked", "calm", "stale", "empty"] as const) {
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
