import { expect, test, type Page, type Route } from "@playwright/test";
import type {
  IntelligenceState,
  IntelligenceWorkspace,
  WorkspaceMarket,
  WorkspaceMatch,
  WorkspaceRisks,
} from "../src/types/intelligenceWorkspace";

const STATES: IntelligenceState[] = [
  "COLLECTION_INCIDENT",
  "DATA_INCOMPLETE",
  "MODEL_DIAGNOSTIC_WARNING",
  "MARKET_ANOMALY",
  "MODEL_MARKET_DISAGREEMENT",
  "MARKET_MOVEMENT",
  "MARKET_STABLE",
];

async function expectDeterministicScreenshot(page: Page): Promise<void> {
  await page.addStyleTag({ content: "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}html{scroll-behavior:auto!important}" });
  const first = await page.screenshot({ animations: "disabled", fullPage: false });
  const second = await page.screenshot({ animations: "disabled", fullPage: false });
  expect(second.equals(first)).toBe(true);
}

function risks(attention?: keyof WorkspaceRisks): WorkspaceRisks {
  return Object.fromEntries(["EVENT_RISK", "DATA_RISK", "MODEL_RISK", "COLLECTION_RISK"].map((axis) => [axis, {
    dimension: axis,
    status: axis === attention ? "ATTENTION" : "OK",
    reason_codes: axis === attention ? [`${axis}_ATTENTION`] : [],
    explanation: axis === attention ? `${axis} requires review` : `No current ${axis} evidence`,
  }])) as WorkspaceRisks;
}

function market(name: "ASIAN_HANDICAP" | "TOTALS", count: number): WorkspaceMarket {
  const snapshotState = count === 0 ? "NO_TIMELINE_EVIDENCE" : count === 1 ? "ONE_OBSERVATION_NOT_A_TREND" : "DISCRETE_REAL_PATH";
  return {
    market: name,
    status: count ? "READY" : "INSUFFICIENT",
    snapshot_state: snapshotState,
    snapshot_count: count,
    observation_count: count * 4,
    main_line: count ? (name === "ASIAN_HANDICAP" ? "-0.25" : "2.5") : null,
    bookmaker_count: count ? 4 : 0,
    prices: count ? { HOME: 1.94, AWAY: 1.96 } : {},
    probabilities: count ? { HOME: 0.505, AWAY: 0.495 } : {},
    freshness: { status: count ? "FRESH" : "NOT_AVAILABLE" },
    timeline_points: Array.from({ length: count }, (_, index) => ({
      capture_id: `${name.toLowerCase()}-${index + 1}`,
      captured_at: `2026-08-09T0${index + 1}:00:00Z`,
      canonical_line: name === "ASIAN_HANDICAP" ? "-0.25" : "2.5",
      bookmaker_count: 4,
      prices: { HOME: 1.94 + index / 100 },
      probabilities: { HOME: 0.505 - index / 100 },
    })),
    movement: { status: count >= 2 ? "STABLE" : "INSUFFICIENT" },
    reason_codes: count >= 2 ? ["DISCRETE_REAL_PATH"] : [snapshotState],
  };
}

function match(fixtureId: string, state: IntelligenceState, snapshotCount: number): WorkspaceMatch {
  const matchRisks = risks(state === "COLLECTION_INCIDENT" ? "COLLECTION_RISK" : state === "DATA_INCOMPLETE" ? "DATA_RISK" : state === "MODEL_DIAGNOSTIC_WARNING" ? "MODEL_RISK" : undefined);
  const relation = (marketName: "ASIAN_HANDICAP" | "TOTALS") => ({
    market: marketName,
    status: state === "MODEL_MARKET_DISAGREEMENT" ? "MODEL_OUTSIDE_MARKET_RANGE" : "COMPARABLE_WITHIN_MARKET_RANGE",
    canonical_line: marketName === "ASIAN_HANDICAP" ? "-0.25" : "2.5",
    bookmaker_count: 4,
    freshness_status: "FRESH",
    diagnostics: state === "MODEL_MARKET_DISAGREEMENT" ? [{ selection: "HOME", model: 0.61, market_median: 0.5 }] : [],
    blockers: [],
  });
  return {
    fixture_id: fixtureId,
    competition_id: "premier_league",
    competition_name: "Premier League",
    kickoff_utc: "2026-08-10T12:00:00Z",
    home_team_name: `Home ${fixtureId}`,
    away_team_name: `Away ${fixtureId}`,
    status: "NS",
    intelligence_state: state,
    intelligence_reason_codes: [`${state}_FACTUAL_EVIDENCE`],
    risks: matchRisks,
    readiness: {
      status: state === "DATA_INCOMPLETE" ? "BLOCKED" : "READY",
      reason_code: state === "DATA_INCOMPLETE" ? "LINEUPS_NOT_READY" : "EVIDENCE_READY",
      reason_codes: [`${state}_FACTUAL_EVIDENCE`],
      missing_fields: state === "DATA_INCOMPLETE" ? ["lineups"] : [],
      stale_fields: [],
      action: "WAIT_FOR_NEXT_SCHEDULED_EVALUATION",
      next_eval_at: "2026-08-10T11:00:00Z",
      provider_budget_status: "PROTECTED",
      lineup_status: state === "DATA_INCOMPLETE" ? "PROVIDER_EMPTY" : "AVAILABLE",
      lineup_expectation: "EXPECTED_NEAR_KICKOFF",
    },
    market_fact: {
      status: snapshotCount ? "READY" : "INSUFFICIENT",
      main_line: snapshotCount ? "-0.25" : null,
      current_odds: snapshotCount ? { HOME: 1.94, AWAY: 1.96 } : {},
      market_probabilities: snapshotCount ? { HOME: 0.505, AWAY: 0.495 } : {},
      price_reference: "LAST_AVAILABLE_PREMATCH_SNAPSHOT",
      canonical_close_status: "NOT_OBTAINABLE_FROM_CURRENT_PROVIDER",
    },
    w2_analysis: {
      status: "ANALYSIS_REFERENCE",
      proof_status: "NOT_PROVEN",
      decision_tier: state === "DATA_INCOMPLETE" ? "NOT_READY" : "WATCH",
      analysis_state: state,
      reason_codes: [`${state}_FACTUAL_EVIDENCE`],
      model_view: { status: "READY", model_version: "w2-existing-v1", calibration_version: "cal-v1", calibration_status: "AVAILABLE", simulations_completed: 10_000 },
      model_market_relation: { ASIAN_HANDICAP: relation("ASIAN_HANDICAP"), TOTALS: relation("TOTALS") },
    },
    formal_recommendation: { status: "OFF", reason: "PRODUCT_AUTHORITY_DISABLED" },
    market_radar: { schema_version: "w2.market-radar.v1", markets: { ASIAN_HANDICAP: market("ASIAN_HANDICAP", snapshotCount), TOTALS: market("TOTALS", snapshotCount) } },
    model_lab: {
      schema_version: "w2.model-lab.v1",
      w2_model: { status: "READY", model_version: "w2-existing-v1", calibration_status: "AVAILABLE" },
      market: {
        ASIAN_HANDICAP: { status: snapshotCount ? "READY" : "INSUFFICIENT", main_line: snapshotCount ? "-0.25" : null, bookmaker_count: snapshotCount ? 4 : 0, freshness: { status: snapshotCount ? "FRESH" : "NOT_AVAILABLE" } },
        TOTALS: { status: snapshotCount ? "READY" : "INSUFFICIENT", main_line: snapshotCount ? "2.5" : null, bookmaker_count: snapshotCount ? 4 : 0, freshness: { status: snapshotCount ? "FRESH" : "NOT_AVAILABLE" } },
      },
      api_football_prediction: { status: "NOT_AVAILABLE", role: "EXTERNAL_MODEL_BENCHMARK", reason_code: "API_FOOTBALL_PREDICTION_NOT_PROJECTED" },
      relation: { ASIAN_HANDICAP: relation("ASIAN_HANDICAP"), TOTALS: relation("TOTALS") },
      historical_validation: { final_verdict: "NO_EDGE", v_continuation_gate: "FAIL", historical_incremental_edge: "NOT_PROVEN", h_result_access: "PERMANENTLY_CLOSED", reexecuted: false },
    },
    scoreline_reference: snapshotCount === 2 ? {
      label: "MODEL_SCORELINE_REFERENCE", proof_status: "NOT_PROVEN", status: "READY", simulations_completed: 10_000,
      top3: [
        { scoreline: "1-0", unconditional_probability: 0.15, sample_count: 1500 },
        { scoreline: "1-1", unconditional_probability: 0.12, sample_count: 1200 },
        { scoreline: "0-0", unconditional_probability: 0.1, sample_count: 1000 },
      ],
    } : { label: "MODEL_SCORELINE_REFERENCE", proof_status: "NOT_PROVEN", status: "UNAVAILABLE", simulations_completed: null, top3: [] },
    evidence: { card_hash: `card-${fixtureId}`, artifact_hash: `artifact-${fixtureId}`, source: "decision_contract", source_event_at: "2026-08-09T02:00:00Z", decision_role: "DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY" },
  };
}

function workspace(scenario = "default"): IntelligenceWorkspace {
  let matches = [match("zero", "DATA_INCOMPLETE", 0), match("one", "MODEL_MARKET_DISAGREEMENT", 1), match("two", "MARKET_STABLE", 2)];
  if (scenario === "empty") matches = [];
  if (scenario === "seven-states") matches = STATES.map((state, index) => match(`state-${index}`, state, index % 3));
  const attention = matches.map((item) => ({
    fixture_id: item.fixture_id,
    kickoff_utc: item.kickoff_utc,
    intelligence_state: item.intelligence_state,
    reason_codes: item.intelligence_reason_codes,
    affected_domains: [item.intelligence_state.split("_")[0]],
    factual_summary: `${item.intelligence_state}: ${item.intelligence_reason_codes.join(", ")}`,
    readiness_status: item.readiness.status,
    readiness_context: { reason_code: item.readiness.reason_code, missing_fields: item.readiness.missing_fields, stale_fields: item.readiness.stale_fields, action: item.readiness.action },
    next_eval_at: item.readiness.next_eval_at,
    risks: item.risks,
  }));
  const payload: IntelligenceWorkspace = {
    request_id: "e2e-unified",
    schema_version: "w2.dashboard-intelligence-workspace.v1",
    generated_at: "2026-08-09T02:00:00Z",
    date: "2026-08-09",
    timezone: "Asia/Shanghai",
    window: "today",
    source: "dashboard_day_view+performance_checkpoint+replay_front_door",
    selected_fixture_id: matches.at(-1)?.fixture_id || null,
    read_contract: { provider_calls: 0, db_writes: 0, would_write_checkpoint: false, no_call_on_read: true },
    runtime: { product: "FOOTBALL_MARKET_INTELLIGENCE_PLUS_MODEL_DIAGNOSTICS", public_dashboard_authority: "NEW_INTELLIGENCE_WORKSPACE_ONLY", active_whitelist_count: 13, free_bridge_mode: "SHADOW_ONLY", candidate: "OFF", formal: "OFF", lock: "OFF", production: "OFF" },
    navigation: { current_date: "2026-08-09" },
    attention,
    matches,
    validation: {
      probability: { status: "SAMPLE_BUILDING", sample_count: 12, model_brier: 0.21, market_brier: 0.22, model_minus_market_brier: -0.01, model_log_loss: 0.61, market_log_loss: 0.62, model_minus_market_log_loss: -0.01, model_calibration_error: 0.04, market_calibration_error: 0.05, model_reliability_bins: [{ lower: 0.4, upper: 0.5, count: 6, mean_confidence: 0.46, accuracy: 0.5 }], market_reliability_bins: [{ lower: 0.4, upper: 0.5, count: 6, mean_confidence: 0.48, accuracy: 0.5 }], checkpoint_metadata: { checkpoint_key: "performance:cohort:all" } },
      directional: { status: "SAMPLE_BUILDING", validation_n: 12, decisive_n: 6, correct: 4, wrong: 2, push: 1, void: 1, direction_accuracy: 4 / 6, effective_n: 6, market_direction_benchmark: "NOT_DEFINED" },
      league_performance: [{ league: "Premier League", validation_n: 12, decisive_n: 6, correct: 4, wrong: 2, push: 1, void: 1, direction_accuracy: 4 / 6, brier: 0.21, calibration: 0.04, statistical_status: "SAMPLE_BUILDING" }],
      forward_validation_records: { status: "AVAILABLE", validation_count: 12, eligible_count: 8, excluded_count: 2, pending_count: 2, outcomes: { hit_count: 4, miss_count: 2, push_count: 1, void_count: 1 }, checkpoint_metadata: { checkpoint_key: "performance:cohort:all" } },
      history_replay: { status: "AVAILABLE_WITH_GAPS", known_at: { has_day_view: true, generated_at: "2026-08-09T02:00:00Z", source: "dashboard_read_model", checkpoint_key: "dashboard:day_view:2026-08-09" }, decision_summary: { total_cards: matches.length, lock_eligible_count: 0, by_decision_tier: { WATCH: matches.length }, by_data_status: { READY: Math.max(matches.length - 1, 0) } }, reason_summary: [{ reason_code: "MARKET_STABLE_ALL_AVAILABLE_MARKETS", count: 1 }], outcome_tracking_summary: { tracked_count: 8, matched_outcome_count: 6, missing_outcome_count: 2 }, card_hash_checks: [{ fixture_id: "two", status: "MATCH" }], replay_gaps: ["MISSING_OUTCOMES_FOR_2_FIXTURES"] },
    },
    external_intelligence: { weather: { status: "NOT_CONNECTED", affects_match_readiness: false }, news: { status: "NOT_CONNECTED", affects_match_readiness: false }, sentiment: { status: "NOT_CONNECTED", affects_match_readiness: false }, advanced_xg: { status: "NOT_CONNECTED", affects_match_readiness: false } },
    freshness: { domains: Object.fromEntries(["fixtures", "events", "statistics", "players", "lineups", "odds_prematch", "odds_live", "injuries", "predictions", "standings", "teams_statistics", "page_projection"].map((domain) => [domain, { domain: domain.toUpperCase(), availability: domain === "odds_live" ? "FORBIDDEN_AS_BENCHMARK" : "AVAILABLE", status: domain === "events" ? "NOT_AVAILABLE" : "AVAILABLE", source: domain === "events" ? "not_projected" : `${domain}_checkpoint`, source_as_of: domain === "events" ? null : "2026-08-09T02:00:00Z", provider_refresh_authority: "SCHEDULED_ONLY", readiness_semantics: domain === "events" ? "SOURCE_AS_OF_NOT_PROJECTED" : "SOURCE_VALUE_ONLY", no_call_on_read: true }])) },
    data_operations: { read_model_source: "dashboard_read_model", checkpoint_key: "dashboard:day_view:2026-08-09", degradation: { state: scenario === "empty" ? "EMPTY_DAY" : "HEALTHY" }, counts: { total: matches.length }, system_health: scenario === "collection-incident" ? "DEGRADED" : "HEALTHY", provider_budget_status: scenario === "collection-incident" ? "PROTECTED_DEGRADED" : "PROTECTED" },
  };
  const first = payload.matches[0];
  if (first && scenario === "lineup-too-early") { first.readiness.lineup_expectation = "NOT_EXPECTED_YET"; first.readiness.lineup_status = "TOO_EARLY"; first.readiness.reason_code = "LINEUP_WINDOW_NOT_OPEN"; }
  if (first && scenario === "lineup-absent") { first.readiness.lineup_expectation = "EXPECTED"; first.readiness.lineup_status = "PROVIDER_EMPTY"; first.readiness.reason_code = "LINEUP_EXPECTED_BUT_ABSENT"; }
  if (first && scenario === "injuries-stale") { first.readiness.stale_fields = ["injuries"]; first.intelligence_reason_codes = ["INJURIES_STALE"]; }
  if (first && scenario === "market-stale") { first.market_radar.markets.ASIAN_HANDICAP.freshness = { status: "STALE" }; first.intelligence_reason_codes = ["MARKET_STALE"]; }
  if (first && scenario === "collection-incident") { first.intelligence_state = "COLLECTION_INCIDENT"; first.intelligence_reason_codes = ["COLLECTION_PROVIDER_INCIDENT"]; }
  if (first && scenario === "model-not-ready") { first.w2_analysis.model_view.status = "UNAVAILABLE"; first.model_lab.w2_model.status = "UNAVAILABLE"; first.intelligence_reason_codes = ["MODEL_SIMULATION_NOT_READY"]; }
  if (scenario === "validation-insufficient") { payload.validation.probability.status = "INSUFFICIENT"; payload.validation.probability.sample_count = 0; payload.validation.probability.model_reliability_bins = []; payload.validation.probability.market_reliability_bins = []; payload.validation.directional.status = "INSUFFICIENT"; payload.validation.directional.effective_n = 0; }
  if (first && !["default", "empty", "seven-states", "validation-insufficient"].includes(scenario)) payload.selected_fixture_id = first.fixture_id;
  return payload;
}

async function json(route: Route, body: unknown): Promise<void> {
  await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
}

async function installWorkspace(page: Page, scenario = "default"): Promise<string[]> {
  const apiReads: string[] = [];
  await page.clock.install({ time: new Date("2026-08-09T06:00:00Z") });
  await page.route("**/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    apiReads.push(path);
    if (path === "/v1/dashboard/intelligence-workspace") return json(route, workspace(scenario));
    return route.fulfill({ status: 418, json: { error: "LEGACY_ENDPOINT_FORBIDDEN" } });
  });
  return apiReads;
}

test.use({ viewport: { width: 1536, height: 1024 }, locale: "en-GB", timezoneId: "Asia/Shanghai", deviceScaleFactor: 1 });

test("public root consumes only the unified read model and exposes every P3/P4 surface", async ({ page }) => {
  const reads = await installWorkspace(page);
  await page.goto("/");
  await expect(page.locator(".unified-workspace")).toHaveAttribute("data-schema-version", "w2.dashboard-intelligence-workspace.v1");
  await expect(page.locator(".unified-workspace")).toHaveAttribute("data-public-authority", "NEW_INTELLIGENCE_WORKSPACE_ONLY");
  for (const surface of ["attention", "match-board", "match-inspector", "market-radar", "model-lab", "scoreline-top3", "validation", "league-performance", "history-replay", "external-intelligence", "data-operations"]) await expect(page.locator(`[data-ui='${surface}']`)).toBeVisible();
  await expect(page.locator(".workspace-topbar")).toContainText("13 LEAGUES");
  await expect(page.locator(".workspace-topbar")).toContainText("SHADOW_ONLY");
  await expect(page.locator(".workspace-topbar")).toContainText("FORMAL OFF");
  expect(new Set(reads)).toEqual(new Set(["/v1/dashboard/intelligence-workspace"]));
});

test("all seven intelligence states and the exact four risk axes render without semantic promotion", async ({ page }) => {
  await installWorkspace(page, "seven-states");
  await page.goto("/");
  for (const state of STATES) await expect(page.locator(`[data-intelligence-state='${state}']`).first()).toBeVisible();
  const inspector = page.locator("[data-ui='match-inspector']");
  for (const axis of ["EVENT_RISK", "DATA_RISK", "MODEL_RISK", "COLLECTION_RISK"]) await expect(inspector.locator(`[data-risk-axis='${axis}']`)).toHaveCount(1);
  await expect(inspector).toContainText("ANALYSIS_REFERENCE");
  await expect(inspector).toContainText("NOT_PROVEN");
  await expect(inspector).toContainText("PRODUCT_AUTHORITY_DISABLED");
});

test("zero one and two-plus snapshots remain factual discrete evidence", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  for (const [fixture, state, points] of [["zero", "NO_TIMELINE_EVIDENCE", "0"], ["one", "ONE_OBSERVATION_NOT_A_TREND", "1"], ["two", "DISCRETE_REAL_PATH", "2"]] as const) {
    await page.locator(`[data-fixture-id='${fixture}']`).click();
    const timeline = page.locator(`[data-snapshot-state='${state}']`).first();
    await expect(timeline).toHaveAttribute("data-real-point-count", points);
    await expect(timeline.locator("svg, canvas, polyline")).toHaveCount(0);
  }
});

test("scoreline READY is exactly 10000 with unconditional probability and sample count", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  const scoreline = page.locator("[data-ui='scoreline-top3']");
  await expect(scoreline).toContainText("simulations_completed=10000");
  await expect(scoreline).toContainText("unconditional_probability");
  await expect(scoreline).toContainText("sample_count=1500");
  await expect(scoreline).toContainText("15.0%");
  await expect(scoreline).not.toContainText("generic probability");
});

for (const [scenario, expected] of [
  ["lineup-too-early", "NOT_EXPECTED_YET / TOO_EARLY"],
  ["lineup-absent", "EXPECTED / PROVIDER_EMPTY"],
  ["injuries-stale", "INJURIES_STALE"],
  ["market-stale", "STALE"],
  ["collection-incident", "PROTECTED_DEGRADED"],
  ["model-not-ready", "MODEL_SIMULATION_NOT_READY"],
  ["validation-insufficient", "INSUFFICIENT"],
] as const) {
  test(`truth scenario ${scenario} stays explicit`, async ({ page }) => {
    await installWorkspace(page, scenario);
    await page.goto("/");
    await expect(page.locator(".workspace-main")).toContainText(expected);
  });
}

test("SAMPLE_BUILDING, external NOT_CONNECTED, replay evidence and replay gaps are explicit", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  await expect(page.locator("[data-ui='validation']")).toContainText("SAMPLE_BUILDING");
  await expect(page.locator("[data-ui='validation']")).toContainText("NOT_DEFINED");
  await expect(page.locator("[data-ui='external-intelligence'] strong")).toHaveCount(4);
  await expect(page.locator("[data-ui='external-intelligence']")).toContainText("NOT_CONNECTED");
  await expect(page.locator("[data-ui='external-intelligence']")).toContainText("affects_match_readiness=false");
  await expect(page.locator("[data-ui='history-replay']")).toContainText("AVAILABLE_WITH_GAPS");
  await expect(page.locator("[data-ui='history-replay']")).toContainText("MISSING_OUTCOMES_FOR_2_FIXTURES");
  await expect(page.locator("[data-ui='history-replay']")).toContainText("Hash checks1");
});

test("empty day is explicit and never fabricates a match", async ({ page }) => {
  await installWorkspace(page, "empty");
  await page.goto("/");
  await expect(page.locator("[data-ui='match-board']")).toContainText("Empty football day");
  await expect(page.locator(".match-board-row")).toHaveCount(0);
  await expect(page.locator("[data-ui='match-inspector']")).toContainText("No selected fixture");
});

test("public copy excludes forbidden decision and commercial semantics", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  const body = page.locator("body");
  for (const forbidden of ["CLV", "ROI", "expected_value", "value_score", "opportunity_score", "market_pick", "anonymous_live_odds_benchmark", "Recommendation Board", "Boss Decision Console"]) await expect(body).not.toContainText(forbidden);
  await expect(body).toContainText("优先检查模型校准、特征时效、盘口身份和数据质量");
  await expect(body).toContainText("Formal recommendation is OFF");
});

test("fixed visual authority is deterministic at 1536x1024 within the browser runtime", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  await expect(page.locator("[data-ui='match-board']")).toBeVisible();
  await expectDeterministicScreenshot(page);
});

for (const viewport of [{ width: 1920, height: 1080 }, { width: 1440, height: 900 }, { width: 1366, height: 768 }]) {
  test(`responsive geometry ${viewport.width}x${viewport.height} has no page overflow`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await installWorkspace(page);
    await page.goto("/");
    const geometry = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }));
    expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.clientWidth);
    await expect(page.locator("[data-ui='attention']")).toBeVisible();
    await expect(page.locator("[data-ui='match-board']")).toBeVisible();
    await expectDeterministicScreenshot(page);
  });
}

test("endpoint failure stays fail-closed without legacy fallback", async ({ page }) => {
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 503, json: { code: "SYSTEM_DEGRADED" } }));
  await page.goto("/");
  await expect(page.locator(".workspace-load-state--error")).toContainText("Unified workspace unavailable");
  await expect(page.locator(".workspace-load-state--error")).toContainText("no legacy dashboard or synthetic data");
});
