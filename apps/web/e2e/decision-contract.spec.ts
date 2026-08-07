import { expect, test, type Page, type Route } from "@playwright/test";

const riskDimensions = {
  EVENT_RISK: { dimension: "EVENT_RISK", status: "OK", reason_codes: [], explanation: "未发现明确赛事风险证据" },
  DATA_RISK: { dimension: "DATA_RISK", status: "OK", reason_codes: [], explanation: "数据证据完整" },
  MODEL_RISK: { dimension: "MODEL_RISK", status: "OK", reason_codes: [], explanation: "模型诊断未见警告" },
  COLLECTION_RISK: { dimension: "COLLECTION_RISK", status: "OK", reason_codes: [], explanation: "采集运行未见异常" },
};

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
      intelligence_reason_codes: ["MODEL_MARKET_DISAGREEMENT_OBSERVED"],
      risk_dimensions: {
        ...riskDimensions,
        MODEL_RISK: { dimension: "MODEL_RISK", status: "ATTENTION", reason_codes: ["MODEL_MARKET_DISAGREEMENT_OBSERVED"], explanation: "模型与市场差异待复核" },
      },
      model_market_divergence: { status: "READY", magnitude: 0.08, direction_allowed: true },
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
      current_odds: { ah: { home_line: "-0.25", home_price: 1.91, away_price: 1.97, captured_at: "2026-08-07T23:54:00Z" } },
      recommendation_decision_v4: { outcome: "NOT_READY" },
    }),
  ];
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
  await expect(page.locator(".decision-counts")).toContainText("市场稳定1");
  await expect(page.locator(".intelligence-ops")).toContainText("Candidate OFF · Formal OFF · Lock OFF · Production OFF");
  await expect(page.locator(".intelligence-ops")).toContainText("e2e0001 / e2e0001 · SYNC");
  expect(consoleErrors).toEqual([]);
});

test("stable state is a meaningful non-empty result", async ({ page }) => {
  await installRoutes(page);
  await page.goto("/");

  const stable = page.locator("[data-intelligence-state='MARKET_STABLE']");
  await expect(stable).toBeVisible();
  await expect(stable).toContainText("市场稳定 / 未检测到显著异常");
  await expect(stable).toContainText("MARKET_STABLE_NO_MATERIAL_ALERT");
});

test("divergence stays diagnostic and never becomes public recommendation semantics", async ({ page }) => {
  await installRoutes(page);
  await page.goto("/");

  const disagreement = page.locator("[data-intelligence-state='MODEL_MARKET_DISAGREEMENT']");
  await expect(disagreement).toContainText("模型与市场存在分歧");
  await expect(disagreement).toContainText("差异仅用于模型校准与特征复核");
  const body = page.locator("body");
  for (const forbidden of ["价值机会", "正 EV 机会", "市场错误定价", "推荐方向", "高置信度选择", "值得介入"]) {
    await expect(body).not.toContainText(forbidden);
  }
});

test("market facts survive V4 not-ready and four risk axes stay separate", async ({ page }) => {
  await installRoutes(page);
  await page.goto("/");

  const notReady = page.locator("[data-ui='match-intelligence-card']").filter({ hasText: "No Pick Home" });
  await expect(notReady).toContainText("当前市场事实");
  await expect(notReady).toContainText("home_line: -0.25");
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
