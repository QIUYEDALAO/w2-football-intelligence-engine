import { expect, test, type Page, type Route } from "@playwright/test";

const riskDimensions = {
  EVENT_RISK: { dimension: "EVENT_RISK", status: "OK", reason_codes: [], explanation: "未发现明确赛事风险证据" },
  DATA_RISK: { dimension: "DATA_RISK", status: "OK", reason_codes: [], explanation: "数据证据完整" },
  MODEL_RISK: { dimension: "MODEL_RISK", status: "OK", reason_codes: [], explanation: "模型诊断未见警告" },
  COLLECTION_RISK: { dimension: "COLLECTION_RISK", status: "OK", reason_codes: [], explanation: "采集运行未见异常" },
};

const statePrecedence = ["COLLECTION_INCIDENT", "DATA_INCOMPLETE", "MODEL_DIAGNOSTIC_WARNING", "MARKET_ANOMALY", "MODEL_MARKET_DISAGREEMENT", "MARKET_MOVEMENT", "MARKET_STABLE"];

const phase05 = {
  protocol: "W2_PHASE_0_5_AH_OU_EDGE_EXISTENCE_PROTOCOL_V1_RC3",
  final_verdict: "NO_EDGE",
  v_continuation_gate: "FAIL",
  ou_pre_best_frozen_selections: 7566,
  ou_pre_best_frozen_strategy_roi: "-5.32%",
  historical_incremental_edge: "NOT_PROVEN",
  h_result_access: "PERMANENTLY_CLOSED",
  reexecuted: false,
};

function timeline(lines: string[]) {
  const points = lines.map((canonical_line, index) => ({
    capture_id: `capture-${index + 1}`,
    captured_at: `2026-08-07T23:${50 + index}:00Z`,
    canonical_line,
    bookmaker_count: 3,
  }));
  return {
    status: points.length === 0 ? "INSUFFICIENT_NO_TIMELINE_EVIDENCE" : points.length === 1 ? "INSUFFICIENT_SINGLE_SNAPSHOT" : "MOVEMENT_COMPARISON_ELIGIBLE",
    valid_snapshot_count: points.length,
    distinct_captured_at_count: points.length,
    same_line_comparable_snapshot_count: points.length,
    points,
  };
}

function card(overrides: Record<string, unknown> = {}) {
  return {
    fixture_id: "stable-fixture",
    kickoff_utc: "2026-08-08T12:00:00Z",
    kickoff_beijing: "2026-08-08 20:00",
    competition_id: "premier_league",
    competition_name: "Premier League",
    home_team_name: "Stable Home",
    away_team_name: "Stable Away",
    status: "NS",
    source: "dashboard_read_model",
    intelligence_state: "MARKET_STABLE",
    intelligence_reason_codes: ["MARKET_STABLE_NO_MATERIAL_ALERT"],
    risk_dimensions: riskDimensions,
    recommendation_decision_v4_role: "DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY",
    decision_tier: "SKIP",
    data_status: "READY",
    lifecycle_status: "DRAFT",
    outcome_tracked: false,
    lock_eligible: false,
    recommendation_id: null,
    missing_fields: [],
    stale_fields: [],
    current_odds: { ou: { line: "2.5", over_price: 1.93, under_price: 1.95, captured_at: "2026-08-07T23:55:00Z" } },
    last_known_odds: {},
    market_probabilities: { over: 0.51, under: 0.49 },
    market_movement: { status: "READY", pattern: "STABLE", line_moved: false },
    model_market_divergence: {},
    market_radar: {
      schema_version: "w2.market-radar.v1",
      authority: "REAL_PERSISTED_MARKET_EVIDENCE",
      evidence: { accepted_observation_count: 6, rejected_observation_count: 0 },
      statistical_anomaly: { calibration_status: "NOT_CALIBRATED", detected: false },
      markets: {
        ASIAN_HANDICAP: { status: "INSUFFICIENT", current: null, snapshot_count: 0, observation_count: 0, timeline: timeline([]), movement: { status: "INSUFFICIENT" }, movement_history: [] },
        TOTALS: { status: "READY", current: { canonical_line: "2.5", bookmaker_count: 3, prices: { OVER: { median: 1.93 }, UNDER: { median: 1.95 } }, freshness: { status: "COMPLETE" } }, snapshot_count: 2, observation_count: 12, timeline: timeline(["2.5", "2.5"]), movement: { status: "STABLE" }, movement_history: [{ status: "STABLE" }] },
      },
    },
    model_lab: {
      schema_version: "w2.model-lab.v1",
      authority: "DIAGNOSTIC_ONLY",
      historical_validation: phase05,
      markets: {
        ASIAN_HANDICAP: { status: "MARKET_NOT_READY", market: "ASIAN_HANDICAP", bookmaker_count: 0, diagnostics: [], blockers: ["MARKET_NOT_READY"] },
        TOTALS: { status: "COMPARABLE_WITHIN_MARKET_RANGE", market: "TOTALS", bookmaker_count: 3, model_version: "model-v1", calibration_status: "READY", diagnostics: [{ selection: "OVER", model_effective_settlement_probability: 0.51, market_probability_median: 0.5, market_probability_min: 0.48, market_probability_max: 0.52, distance_outside_market_range: 0 }], blockers: [] },
      },
    },
    scoreline_picks: [],
    pick: null,
    non_pick: { reason_code: "OBSERVE", action: "WAIT" },
    ...overrides,
  };
}

function dayView(empty = false) {
  const cards = empty ? [] : [
    card(),
    card({
      fixture_id: "disagreement-fixture",
      home_team_name: "Diagnostic Home",
      away_team_name: "Diagnostic Away",
      intelligence_state: "MODEL_MARKET_DISAGREEMENT",
      intelligence_reason_codes: ["MODEL_MARKET_DISAGREEMENT_ASIAN_HANDICAP"],
      risk_dimensions: {
        ...riskDimensions,
        MODEL_RISK: { dimension: "MODEL_RISK", status: "ATTENTION", reason_codes: ["MODEL_MARKET_DISAGREEMENT_ASIAN_HANDICAP"], explanation: "模型与市场差异待复核" },
      },
      model_lab: {
        schema_version: "w2.model-lab.v1",
        authority: "DIAGNOSTIC_ONLY",
        historical_validation: phase05,
        markets: {
          ASIAN_HANDICAP: { status: "MODEL_OUTSIDE_MARKET_RANGE", market: "ASIAN_HANDICAP", bookmaker_count: 4, model_version: "model-v1", calibration_status: "READY", diagnostics: [{ selection: "HOME", model_effective_settlement_probability: 0.63, market_probability_median: 0.51, market_probability_min: 0.49, market_probability_max: 0.53, distance_outside_market_range: 0.1 }], blockers: [] },
          TOTALS: { status: "COMPARABLE_WITHIN_MARKET_RANGE", market: "TOTALS", bookmaker_count: 3, model_version: "model-v1", calibration_status: "READY", diagnostics: [], blockers: [] },
        },
      },
    }),
    card({
      fixture_id: "not-ready-fixture",
      home_team_name: "No Pick Home",
      away_team_name: "No Pick Away",
      intelligence_state: "DATA_INCOMPLETE",
      intelligence_reason_codes: ["DATA_STATUS_BLOCKED", "MODEL_SIMULATION_NOT_READY"],
      risk_dimensions: {
        ...riskDimensions,
        DATA_RISK: { dimension: "DATA_RISK", status: "INCIDENT", reason_codes: ["DATA_STATUS_BLOCKED"], explanation: "数据尚未完整" },
        MODEL_RISK: { dimension: "MODEL_RISK", status: "INCIDENT", reason_codes: ["MODEL_SIMULATION_NOT_READY"], explanation: "模型尚未就绪" },
      },
      decision_tier: "NOT_READY",
      data_status: "BLOCKED",
      market_radar: {
        schema_version: "w2.market-radar.v1",
        authority: "REAL_PERSISTED_MARKET_EVIDENCE",
        evidence: { accepted_observation_count: 6 },
        statistical_anomaly: { calibration_status: "NOT_CALIBRATED", detected: false },
        markets: {
          ASIAN_HANDICAP: { status: "READY", current: { canonical_line: "-0.25", bookmaker_count: 3, prices: { HOME: { median: 1.91 }, AWAY: { median: 1.97 } }, freshness: { status: "COMPLETE" } }, snapshot_count: 1, observation_count: 6, timeline: timeline(["-0.25"]), movement: { status: "INSUFFICIENT" }, movement_history: [] },
          TOTALS: { status: "INSUFFICIENT", current: null, snapshot_count: 0, observation_count: 0, timeline: timeline([]), movement: { status: "INSUFFICIENT" }, movement_history: [] },
        },
      },
      recommendation_decision_v4: { outcome: "NOT_READY" },
    }),
  ].sort((left, right) => statePrecedence.indexOf(String(left.intelligence_state)) - statePrecedence.indexOf(String(right.intelligence_state)));
  return {
    request_id: "e2e",
    generated_at: "2026-08-08T00:00:00Z",
    date: "2026-08-08",
    football_day: "2026-08-08",
    selected_football_day: "2026-08-08",
    environment: "staging",
    timezone: "Asia/Shanghai",
    window: "future",
    source: "dashboard_read_model",
    provider_calls: 0,
    db_writes: 0,
    counts: {
      total: cards.length,
      monitored_fixtures: cards.length,
      market_complete_fixtures: cards.length,
      fresh_quotes: cards.length,
      market_stable_fixtures: empty ? 0 : 1,
      market_movement_fixtures: 0,
      model_diagnostic_warnings: 0,
      data_incidents: empty ? 0 : 1,
      collection_incidents: 0,
      lock_eligible: 0,
      outcome_tracked: 0,
      analysis_pick: 0,
      recommend: 0,
      watch: 0,
      not_ready: empty ? 0 : 1,
      skip: empty ? 0 : 2,
      ready: empty ? 0 : 2,
      partial: 0,
      stale: 0,
      blocked: empty ? 0 : 1,
      identity_not_ready: 0,
      xg_not_ready: empty ? 0 : 1,
      model_ready: empty ? 0 : 2,
      waiting_fresh_quote: 0,
      executable_quote: cards.length,
      no_edge: 0,
      lineup_pending: 0,
      ratings_enhancement_missing: 0,
      team_value_enhancement_missing: 0,
      by_intelligence_state: {
        DATA_INCOMPLETE: empty ? 0 : 1,
        MODEL_MARKET_DISAGREEMENT: empty ? 0 : 1,
        MARKET_STABLE: empty ? 0 : 1,
      },
    },
    freshness: {
      page_updated_at: "2026-08-08T00:00:00Z",
      odds_last_confirmed_at: "2026-08-07T23:55:00Z",
      next_refresh_tick: "2026-08-08T00:15:00Z",
      provider_budget_status: "PROTECTED",
      refreshing: false,
      staleness: { stale_cards: 0, blocked_cards: empty ? 0 : 1, stale_or_blocked_cards: empty ? 0 : 1 },
    },
    degradation: empty ? { title: "当前足球日没有比赛", message: "明确空日，不虚构比赛。" } : {},
    cards,
  };
}

async function json(route: Route, body: unknown): Promise<void> {
  await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
}

async function installRoutes(page: Page, empty = false): Promise<void> {
  await page.route("**/*", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/meta.json") return json(route, { web_git_sha: "e2e0001", release_id: "e2e", data_mode: "api" });
    if (path === "/v1/version") return json(route, {
      service: "w2",
      environment: "staging",
      api_git_sha: "e2e0001",
      release_id: "e2e",
      data_profile: "real-db",
      data_source: "dashboard_read_model",
      database_ready: true,
      read_model_fixture_count: empty ? 0 : 3,
      matchday_card_count: empty ? 0 : 3,
      result_event_count: 0,
      generated_at: "2026-08-08T00:00:00Z",
    });
    if (path === "/v1/formal/tracking/summary") return json(route, null);
    if (path === "/v1/dashboard/day-view") return json(route, dayView(empty));
    return route.continue();
  });
}

test("public root is intelligence-first with truthful operations", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  await installRoutes(page);
  await page.goto("/");

  await expect(page).toHaveTitle("W2 Football Intelligence");
  await expect(page.getByRole("heading", { name: "W2 Football Intelligence" })).toBeVisible();
  await expect(page.getByText("Market Overview", { exact: true })).toBeVisible();
  await expect(page.getByText("Match Intelligence", { exact: true })).toBeVisible();
  await expect(page.getByText("Data & Operations Summary", { exact: true })).toBeVisible();
  await expect(page.locator(".decision-counts")).toContainText("监测比赛3");
  await expect(page.locator(".decision-count")).toHaveCount(5);
  await expect(page.locator(".decision-counts")).toContainText("模型市场分歧1");
  await expect(page.locator("[data-ui='attention-feed'] li").first()).toContainText("DATA_INCOMPLETE");
  await expect(page.locator(".intelligence-ops-details")).toContainText("Candidate OFF · Formal OFF · Lock OFF · Production OFF");
  await expect(page.locator(".intelligence-ops").first()).toContainText("e2e0001 / e2e0001 · SYNC");
  expect(consoleErrors).toEqual([]);
});

test("stable state is a meaningful non-empty result", async ({ page }) => {
  await installRoutes(page);
  await page.goto("/");

  const stable = page.locator("[data-intelligence-state='MARKET_STABLE']");
  await expect(stable).toBeVisible();
  await expect(stable).toContainText("市场稳定 / 未检测到显著异常");
  await expect(stable).toContainText("MARKET_STABLE_NO_MATERIAL_ALERT");
  await expect(stable.locator("[data-ui='market-radar']")).toContainText("主盘口 2.5");
  await expect(stable.locator("[data-ui='model-lab']")).toContainText("COMPARABLE_WITHIN_MARKET_RANGE");
  await expect(stable.locator("[data-ui='phase-0-5-context']")).toContainText("NO_EDGE");
  await expect(stable.locator("[data-ui='phase-0-5-context']")).toContainText("HISTORICAL_INCREMENTAL_EDGE=NOT_PROVEN");
});

test("divergence stays diagnostic and never becomes public recommendation semantics", async ({ page }) => {
  await installRoutes(page);
  await page.goto("/");

  const disagreement = page.locator("[data-intelligence-state='MODEL_MARKET_DISAGREEMENT']");
  await expect(disagreement).toContainText("模型与市场存在分歧");
  await expect(disagreement).toContainText("优先检查模型校准、特征时效、盘口身份和数据质量");
  const body = page.locator("body");
  for (const forbidden of ["价值机会", "正 EV 机会", "市场错误定价", "推荐方向", "高置信度选择", "值得介入"]) {
    await expect(body).not.toContainText(forbidden);
  }
});

test("zero one and multi-point timelines never fabricate a movement path", async ({ page }) => {
  await installRoutes(page);
  await page.goto("/");

  const stable = page.locator("[data-intelligence-state='MARKET_STABLE']");
  const emptyTimeline = stable.locator("[data-timeline-state='INSUFFICIENT_NO_TIMELINE_EVIDENCE']");
  await expect(emptyTimeline).toHaveAttribute("data-real-point-count", "0");
  await expect(emptyTimeline.locator("polyline")).toHaveCount(0);
  const multiTimeline = stable.locator("[data-timeline-state='MOVEMENT_COMPARISON_ELIGIBLE']");
  await expect(multiTimeline).toHaveAttribute("data-real-point-count", "2");
  await expect(multiTimeline.locator("polyline")).toHaveCount(1);

  const singleTimeline = page.locator("[data-ui='match-intelligence-card']").filter({ hasText: "No Pick Home" }).locator("[data-timeline-state='INSUFFICIENT_SINGLE_SNAPSHOT']");
  await expect(singleTimeline).toHaveAttribute("data-real-point-count", "1");
  await expect(singleTimeline.locator("polyline")).toHaveCount(0);
});

test("market facts survive V4 not-ready and four risk axes stay separate", async ({ page }) => {
  await installRoutes(page);
  await page.goto("/");

  const notReady = page.locator("[data-ui='match-intelligence-card']").filter({ hasText: "No Pick Home" });
  await expect(notReady).toContainText("Market Radar · 市场雷达");
  await expect(notReady).toContainText("主盘口 -0.25");
  await expect(notReady).toContainText("INSUFFICIENT");
  await expect(notReady).toContainText("赛事风险");
  await expect(notReady).toContainText("数据风险");
  await expect(notReady).toContainText("模型风险");
  await expect(notReady).toContainText("采集风险");
});

test("a truly empty day remains explicit without fabricating stable cards", async ({ page }) => {
  await installRoutes(page, true);
  await page.goto("/");

  await expect(page.locator(".intelligence-empty")).toContainText("当前足球日没有比赛");
  await expect(page.locator(".intelligence-empty")).toContainText("明确空日，不虚构比赛");
  await expect(page.locator("[data-ui='match-intelligence-card']")).toHaveCount(0);
  await expect(page.locator(".decision-counts")).toContainText("监测比赛0");
});
