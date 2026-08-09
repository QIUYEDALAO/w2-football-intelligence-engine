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
    ...(axis === "COLLECTION_RISK" ? {
      assessment_status: "ASSESSED_CURRENT",
      evidence_basis: "PERSISTED_TERMINAL_ASSESSMENT",
      source_as_of: "2026-08-09T02:00:00Z",
    } : {}),
  }])) as WorkspaceRisks;
}

function market(name: "ASIAN_HANDICAP" | "TOTALS", count: number): WorkspaceMarket {
  const snapshotState = count === 0 ? "NO_TIMELINE_EVIDENCE" : count === 1 ? "ONE_OBSERVATION_NOT_A_TREND" : "DISCRETE_REAL_PATH";
  const sides = name === "ASIAN_HANDICAP" ? ["HOME", "AWAY"] : ["OVER", "UNDER"];
  return {
    market: name,
    status: count ? "READY" : "INSUFFICIENT",
    source_status: count ? "READY" : "INSUFFICIENT",
    snapshot_state: snapshotState,
    snapshot_count: count,
    observation_count: count * 8,
    bookmaker_pair_count: count * 4,
    quote_row_count: count * 8,
    main_line: count ? (name === "ASIAN_HANDICAP" ? "-0.25" : "2.5") : null,
    bookmaker_count: count ? 4 : 0,
    prices: count ? { [sides[0]]: 1.94, [sides[1]]: 1.96 } : {},
    probabilities: count ? { [sides[0]]: 0.505, [sides[1]]: 0.495 } : {},
    freshness: { status: count ? "FRESH" : "NOT_AVAILABLE" },
    timeline_points: Array.from({ length: count }, (_, index) => ({
      capture_id: `${name.toLowerCase()}-${index + 1}`,
      captured_at: `2026-08-09T0${index + 1}:00:00Z`,
      canonical_line: name === "ASIAN_HANDICAP" ? "-0.25" : "2.5",
      bookmaker_count: 4,
      prices: { [sides[0]]: 1.94 + index / 100, [sides[1]]: 1.96 - index / 100 },
      probabilities: { [sides[0]]: 0.505 - index / 100, [sides[1]]: 0.495 + index / 100 },
    })),
    movement: count >= 2 ? {
      status: "STABLE",
      from_captured_at: `2026-08-09T01:00:00Z`,
      to_captured_at: `2026-08-09T0${count}:00:00Z`,
      line_delta: "0",
      price_delta: { [sides[0]]: 0, [sides[1]]: 0 },
      probability_delta: { [sides[0]]: 0, [sides[1]]: 0 },
    } : { status: "INSUFFICIENT" },
    reason_codes: count >= 2 ? ["DISCRETE_REAL_PATH"] : [snapshotState],
  };
}

function match(fixtureId: string, state: IntelligenceState, snapshotCount: number, primaryMarket: "ASIAN_HANDICAP" | "TOTALS" = "ASIAN_HANDICAP", secondarySnapshotCount = 0): WorkspaceMatch {
  const matchRisks = risks(state === "COLLECTION_INCIDENT" ? "COLLECTION_RISK" : state === "DATA_INCOMPLETE" ? "DATA_RISK" : state === "MODEL_DIAGNOSTIC_WARNING" ? "MODEL_RISK" : undefined);
  const ah = market("ASIAN_HANDICAP", primaryMarket === "ASIAN_HANDICAP" ? snapshotCount : secondarySnapshotCount);
  const totals = market("TOTALS", primaryMarket === "TOTALS" ? snapshotCount : secondarySnapshotCount);
  const primary = primaryMarket === "ASIAN_HANDICAP" ? ah : totals;
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
      source_status: snapshotCount ? "READY" : "INSUFFICIENT",
      main_line: primary.main_line,
      current_odds: primary.prices,
      market_probabilities: primary.probabilities,
      price_reference: "LAST_AVAILABLE_PREMATCH_SNAPSHOT",
      canonical_close_status: "NOT_OBTAINABLE_FROM_CURRENT_PROVIDER",
    },
    w2_analysis: {
      status: "ANALYSIS_REFERENCE",
      proof_status: "NOT_PROVEN",
      decision_tier: state === "DATA_INCOMPLETE" ? "NOT_READY" : "WATCH",
      analysis_state: state,
      reason_codes: [`${state}_FACTUAL_EVIDENCE`],
      model_view: { status: "READY", source_status: "READY", model_version: "w2-existing-v1", calibration_version: "cal-v1", calibration_status: "AVAILABLE", simulations_completed: 10_000 },
      model_market_relation: { ASIAN_HANDICAP: relation("ASIAN_HANDICAP"), TOTALS: relation("TOTALS") },
    },
    formal_recommendation: { status: "OFF", reason: "PRODUCT_AUTHORITY_DISABLED" },
    market_radar: { schema_version: "w2.market-radar.v1", markets: { ASIAN_HANDICAP: ah, TOTALS: totals } },
    model_lab: {
      schema_version: "w2.model-lab.v1",
      w2_model: { status: "READY", source_status: "READY", model_version: "w2-existing-v1", calibration_status: "AVAILABLE" },
      market: {
        ASIAN_HANDICAP: { status: ah.status, source_status: ah.source_status, main_line: ah.main_line, bookmaker_count: ah.bookmaker_count, freshness: ah.freshness },
        TOTALS: { status: totals.status, source_status: totals.source_status, main_line: totals.main_line, bookmaker_count: totals.bookmaker_count, freshness: totals.freshness },
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
  let matches = [match("zero", "DATA_INCOMPLETE", 0), match("one", "MODEL_MARKET_DISAGREEMENT", 1, "TOTALS"), match("two", "MARKET_STABLE", 2, "ASIAN_HANDICAP", 2)];
  if (scenario === "empty") matches = [];
  if (scenario === "seven-states") matches = STATES.map((state, index) => match(`state-${index}`, state, index % 3));
  if (scenario === "layout") matches = [
    match("zero", "DATA_INCOMPLETE", 0),
    match("one", "MODEL_MARKET_DISAGREEMENT", 1, "TOTALS"),
    match("two", "MARKET_STABLE", 2, "ASIAN_HANDICAP", 2),
    match("three", "MARKET_MOVEMENT", 2, "TOTALS", 2),
    match("four", "MODEL_DIAGNOSTIC_WARNING", 1),
    match("five", "MARKET_STABLE", 2, "ASIAN_HANDICAP", 2),
  ];
  if (scenario === "attention-homogeneous") matches = [
    match("blocked-a", "DATA_INCOMPLETE", 0),
    match("blocked-b", "DATA_INCOMPLETE", 0),
    match("blocked-c", "DATA_INCOMPLETE", 0),
  ];
  if (scenario === "attention-repeated-groups") matches = [
    match("collection-a", "COLLECTION_INCIDENT", 0),
    match("collection-b", "COLLECTION_INCIDENT", 0),
    match("data-a", "DATA_INCOMPLETE", 0),
    match("data-b", "DATA_INCOMPLETE", 0),
    match("data-c", "DATA_INCOMPLETE", 0),
    match("data-d", "DATA_INCOMPLETE", 0),
  ];
  if (scenario === "market-stale") matches = [match("stale-memory", "MARKET_MOVEMENT", 2)];
  if (scenario === "default") delete matches[1].market_radar.markets.TOTALS.prices.UNDER;
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
    football_day_timezone: "Asia/Shanghai",
    football_day_cutoff_hour: 12,
    football_day_start_utc: "2026-08-09T04:00:00Z",
    football_day_end_utc: "2026-08-10T04:00:00Z",
    source: "dashboard_day_view+performance_checkpoint+replay_front_door",
    selected_fixture_id: matches.at(-1)?.fixture_id || null,
    read_contract: { provider_calls: 0, db_writes: 0, would_write_checkpoint: false, no_call_on_read: true },
    runtime: { product: "FOOTBALL_MARKET_INTELLIGENCE_PLUS_MODEL_DIAGNOSTICS", public_dashboard_authority: "NEW_INTELLIGENCE_WORKSPACE_ONLY", active_whitelist_count: 13, free_bridge_mode: "SHADOW_ONLY", candidate: "OFF", formal: "OFF", lock: "OFF", production: "OFF" },
    navigation: { current_date: "2026-08-09" },
    attention,
    matches,
    validation: {
      probability: { status: "SAMPLE_BUILDING", sample_count: 12, model_brier: 0.21, market_brier: 0.22, model_minus_market_brier: -0.01, model_log_loss: 0.61, market_log_loss: 0.62, model_minus_market_log_loss: -0.01, model_calibration_error: 0.04, market_calibration_error: 0.05, model_reliability_bins: [{ lower: 0.4, upper: 0.5, count: 6, mean_confidence: 0.46, accuracy: 0.5 }], market_reliability_bins: [{ lower: 0.4, upper: 0.5, count: 6, mean_confidence: 0.48, accuracy: 0.5 }], checkpoint_metadata: { checkpoint_key: "performance:cohort:all" } },
      directional: { status: "SAMPLE_BUILDING", source_status: "AVAILABLE", probability_evidence_ready: false, validation_n: 12, decisive_n: 6, correct: 4, wrong: 2, push: 1, void: 1, direction_accuracy: 4 / 6, effective_n: 6, market_direction_benchmark: "NOT_DEFINED", only_record_reason: "PROBABILITY_QUALITY_NOT_READY" },
      league_performance: [{ league: "premier_league", source_league: "39", source_aliases: ["39", "premier_league"], source_checkpoint_keys: ["performance:cohort:league:39"], scope_group: "top_five", aggregation_status: "SOURCE_CHECKPOINT", competition_id: "premier_league", canonical_competition_id: "premier_league", competition_name: "Premier League", identity_status: "RESOLVED", validation_n: 12, decisive_n: 6, correct: 4, wrong: 2, push: 1, void: 1, direction_accuracy: 4 / 6, brier: 0.21, log_loss: 0.61, calibration: 0.04, statistical_status: "SAMPLE_BUILDING", source_statistical_status: "AVAILABLE", probability_evidence_ready: false, only_record_reason: "PROBABILITY_QUALITY_NOT_READY", market_direction_benchmark: "NOT_DEFINED" }],
      tournament_performance: [],
      forward_validation_records: { status: "AVAILABLE", validation_count: 12, eligible_count: 8, excluded_count: 2, excluded_share: 2 / 12, excluded_by_reason: { MARKET_IDENTITY_NOT_READY: 2 }, pending_count: 2, outcomes: { hit_count: 4, miss_count: 2, push_count: 1, void_count: 1 }, checkpoint_metadata: { checkpoint_key: "performance:cohort:all" } },
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
  if (first && scenario === "market-stale") {
    first.market_radar.markets.ASIAN_HANDICAP.status = "STALE";
    first.market_radar.markets.ASIAN_HANDICAP.freshness = { status: "STALE" };
    first.market_fact.status = "STALE";
    first.model_lab.market.ASIAN_HANDICAP.status = "STALE";
    first.model_lab.relation.ASIAN_HANDICAP.status = "MARKET_NOT_READY";
    first.w2_analysis.model_market_relation.ASIAN_HANDICAP.status = "MARKET_NOT_READY";
    first.intelligence_reason_codes = ["MARKET_STALE"];
  }
  if (first && scenario === "collection-incident") { first.intelligence_state = "COLLECTION_INCIDENT"; first.intelligence_reason_codes = ["COLLECTION_PROVIDER_INCIDENT"]; }
  if (first && scenario === "model-not-ready") { first.w2_analysis.model_view.status = "UNAVAILABLE"; first.model_lab.w2_model.status = "UNAVAILABLE"; first.intelligence_reason_codes = ["MODEL_SIMULATION_NOT_READY"]; }
  if (first && scenario === "collection-unassessed") {
    first.risks.COLLECTION_RISK.status = "ATTENTION";
    first.risks.COLLECTION_RISK.assessment_status = "UNASSESSED";
    first.risks.COLLECTION_RISK.evidence_basis = "NO_PERSISTED_TERMINAL_ASSESSMENT";
    first.risks.COLLECTION_RISK.source_as_of = null;
    first.risks.COLLECTION_RISK.reason_codes = ["COLLECTION_ASSESSMENT_NOT_AVAILABLE"];
  }
  if (first && scenario === "baseline-prior") {
    first.w2_analysis.model_view.status = "PRIOR_ONLY";
    first.w2_analysis.model_view.source_status = "READY";
    first.w2_analysis.model_view.calibration_status = "BASELINE_PRIOR";
    first.model_lab.w2_model.status = "PRIOR_ONLY";
    first.model_lab.w2_model.source_status = "READY";
    first.model_lab.w2_model.calibration_status = "BASELINE_PRIOR";
  }
  if (scenario === "validation-insufficient") { payload.validation.probability.status = "INSUFFICIENT"; payload.validation.probability.sample_count = 0; payload.validation.probability.model_reliability_bins = []; payload.validation.probability.market_reliability_bins = []; payload.validation.directional.status = "INSUFFICIENT"; payload.validation.directional.effective_n = 0; }
  if (scenario === "validation-metadata-missing") payload.validation.probability.checkpoint_metadata = {};
  if (scenario === "tournament-truth") payload.validation.tournament_performance = [{
    league: "world_cup_2026", source_league: "1", source_aliases: ["1", "world_cup_2026"], source_checkpoint_keys: ["performance:cohort:league:1"], scope_group: "tournament", aggregation_status: "SOURCE_CHECKPOINT", competition_id: "world_cup_2026", canonical_competition_id: "world_cup_2026", competition_name: "World Cup", identity_status: "RESOLVED", validation_n: 8, decisive_n: 4, correct: 3, wrong: 1, push: 0, void: 0, direction_accuracy: 0.75, brier: null, log_loss: null, calibration: null, statistical_status: "SAMPLE_BUILDING", source_statistical_status: "AVAILABLE", probability_evidence_ready: false, only_record_reason: "PROBABILITY_QUALITY_NOT_READY", market_direction_benchmark: "NOT_DEFINED",
  }];
  if (scenario === "d13-truth") {
    payload.generated_at = "2026-08-09T06:00:00Z";
    payload.selected_fixture_id = matches[0].fixture_id;
    matches[0].readiness.next_eval_at = "2026-08-09T05:00:00Z";
    matches[0].readiness.lineup_expectation = "ADVISORY";
    matches[0].readiness.reason_code = "IDENTITY_NOT_READY";
    matches[0].model_lab.market.ASIAN_HANDICAP.status = "INSUFFICIENT";
    matches[0].model_lab.market.TOTALS.status = "INSUFFICIENT";
    matches[0].model_lab.relation.ASIAN_HANDICAP.status = "MARKET_NOT_READY";
    payload.attention[0].next_eval_at = matches[0].readiness.next_eval_at;
    payload.validation.probability.status = "INSUFFICIENT";
    payload.validation.probability.model_brier = null;
    payload.validation.probability.market_brier = null;
    payload.validation.probability.model_log_loss = null;
    payload.validation.probability.model_calibration_error = null;
    payload.validation.directional.status = "SAMPLE_BUILDING";
    payload.validation.directional.source_status = "AVAILABLE";
    payload.validation.directional.probability_evidence_ready = false;
    payload.validation.directional.direction_accuracy = 0.8;
    payload.validation.directional.effective_n = 5;
    payload.validation.league_performance = [
      { league: "eliteserien", source_league: "103", source_aliases: ["103", "eliteserien"], source_checkpoint_keys: ["performance:cohort:league:103"], scope_group: "national_leagues", aggregation_status: "SOURCE_CHECKPOINT", competition_id: "eliteserien", canonical_competition_id: "eliteserien", competition_name: "Eliteserien", identity_status: "RESOLVED", validation_n: 5, decisive_n: 5, correct: 4, wrong: 1, push: 0, void: 0, direction_accuracy: 0.8, brier: null, log_loss: null, calibration: null, statistical_status: "SAMPLE_BUILDING", source_statistical_status: "AVAILABLE", probability_evidence_ready: false, only_record_reason: "PROBABILITY_QUALITY_NOT_READY", market_direction_benchmark: "NOT_DEFINED" },
      { league: "999", source_league: "999", source_aliases: ["999"], source_checkpoint_keys: ["performance:cohort:league:999"], scope_group: "unresolved", aggregation_status: "SOURCE_CHECKPOINT", competition_id: "999", canonical_competition_id: null, competition_name: null, identity_status: "UNRESOLVED", validation_n: 2, decisive_n: 1, correct: 1, wrong: 0, push: 0, void: 0, direction_accuracy: 1, brier: null, log_loss: null, calibration: null, statistical_status: "SAMPLE_BUILDING", source_statistical_status: "AVAILABLE", probability_evidence_ready: false, only_record_reason: "PROBABILITY_QUALITY_NOT_READY", market_direction_benchmark: "NOT_DEFINED" },
    ];
    payload.validation.forward_validation_records = { ...payload.validation.forward_validation_records, validation_count: 56, eligible_count: 16, excluded_count: 40, excluded_share: 40 / 56, pending_count: 0, excluded_by_reason: { MARKET_IDENTITY_NOT_READY: 25, SCORELINE_NOT_READY: 10, RESULT_MISSING: 5 } };
    payload.data_operations.provider_budget_status = "UNKNOWN";
  }
  if (scenario === "layout") {
    const selected = matches.at(-1)!;
    selected.market_radar.markets.ASIAN_HANDICAP.prices = {
      HOME: { median: 1.89, min: 1.8, max: 1.9 },
      AWAY: { median: 1.955, min: 1.87, max: 1.97 },
    };
    selected.market_radar.markets.ASIAN_HANDICAP.movement.status = "PRICE_MOVEMENT";
    selected.market_radar.markets.ASIAN_HANDICAP.movement.from_captured_at = "2026-08-09T01:00:00Z";
    selected.market_radar.markets.ASIAN_HANDICAP.movement.to_captured_at = "2026-08-09T02:00:00Z";
    selected.market_radar.markets.ASIAN_HANDICAP.movement.line_delta = "0";
    selected.market_radar.markets.ASIAN_HANDICAP.movement.price_delta = { HOME: 0.01, AWAY: -0.01 };
    payload.attention[0].reason_codes = ["DATA_FIELD_STALE"];
    payload.data_operations.system_health = "BLOCKED_DAY";
  }
  if (first && !["default", "empty", "seven-states", "validation-insufficient", "layout"].includes(scenario)) payload.selected_fixture_id = first.fixture_id;
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

test.use({ viewport: { width: 1536, height: 1024 }, locale: "zh-CN", timezoneId: "Asia/Shanghai", deviceScaleFactor: 1 });

test("public root consumes only the unified read model and exposes every P3/P4 surface", async ({ page }) => {
  const reads = await installWorkspace(page);
  await page.goto("/");
  await expect(page.locator(".unified-workspace")).toHaveAttribute("data-schema-version", "w2.dashboard-intelligence-workspace.v1");
  await expect(page.locator(".unified-workspace")).toHaveAttribute("data-public-authority", "NEW_INTELLIGENCE_WORKSPACE_ONLY");
  for (const surface of ["attention", "match-board", "match-inspector", "market-radar", "model-lab", "scoreline-top3", "validation", "league-performance", "history-replay", "external-intelligence", "data-operations"]) await expect(page.locator(`[data-ui='${surface}']`)).toBeVisible();
  await expect(page.locator(".workspace-topbar")).toContainText("13 联赛");
  await expect(page.locator(".workspace-topbar")).toContainText("SHADOW_ONLY");
  await expect(page.locator(".workspace-topbar")).toContainText("FORMAL OFF");
  await expect(page.locator(".workspace-sidebar nav")).toContainText("关注情报");
  await expect(page.locator(".workspace-sidebar nav")).not.toContainText("Attention");
  expect(new Set(reads)).toEqual(new Set(["/v1/dashboard/intelligence-workspace"]));
});

test("ORC-01 Match Board identifies AH and OU main-line facts without side semantics", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  const facts = await page.locator(".match-board-market").allTextContents();
  expect(facts).toEqual(["盘口暂不可用", "大小球 2.5", "让球 -0.25"]);
  expect(facts.every((value) => !/(HOME|AWAY|OVER|UNDER)/.test(value))).toBe(true);
});

test("ORC-02 Market Radar renders two-sided prices and explicitly marks missing evidence", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  const radar = page.locator("[data-ui='market-radar']");
  const ah = radar.locator("[data-market='ASIAN_HANDICAP'] [data-ui='market-prices']");
  const totals = radar.locator("[data-market='TOTALS'] [data-ui='market-prices']");
  await expect(ah).toContainText("主队");
  await expect(ah).toContainText("客队");
  await expect(ah).toContainText("1.94");
  await expect(ah).toContainText("1.96");
  await expect(totals).toContainText("大");
  await expect(totals).toContainText("小");
  await page.locator("[data-fixture-id='zero']").click();
  await expect(radar.locator(".market-prices p")).toHaveCount(2);
  await expect(radar.locator(".market-prices p").first()).toHaveText("暂无价格证据");
  await page.locator("[data-fixture-id='one']").click();
  await expect(totals.locator(":scope > span")).toHaveCount(2);
  await expect(totals.locator("[data-price-side='OVER']")).toContainText("1.94");
  await expect(totals.locator("[data-price-side='UNDER']")).toHaveText("小暂无");
});

test("ORC-03 Probability Validation exposes source checkpoint identity", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  await expect(page.locator("[data-ui='validation-checkpoint']")).toContainText("checkpoint_key=performance:cohort:all");
});

test("ORC-04 League Performance includes Decisive N and its source value", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  const table = page.locator("[data-ui='league-performance']");
  await expect(table.locator(".league-table-head")).toContainText("有效 N");
  await expect(table.locator(".league-table-row > span").nth(1)).toHaveText("6");
});

test("ORC-05 compact header exposes source update time and system health", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  const context = page.locator("[data-ui='header-context']");
  await expect(context).toContainText("更新 2026-08-09 10:00");
  await expect(context).toContainText("系统 健康");
});

test("ORC-06 Scoreline shows model and readiness context for ready and unavailable states", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  const scoreline = page.locator("[data-ui='scoreline-top3']");
  const context = scoreline.locator("[data-ui='scoreline-context']");
  await expect(context.locator("span").nth(0)).toContainText("模型状态就绪");
  await expect(context.locator("span").nth(1)).toContainText("比赛就绪就绪");
  await page.locator("[data-fixture-id='zero']").click();
  await expect(scoreline).toContainText("不可用");
  await expect(context.locator("span").nth(1)).toContainText("比赛就绪阻塞");
  await expect(context.locator("span").nth(2)).toContainText("阻塞原因阵容信息未就绪");
  await expect(scoreline.locator(".technical-details")).toContainText("LINEUPS_NOT_READY");
});

test("D13 truth rendering fails closed without changing source evidence", async ({ page }) => {
  await installWorkspace(page, "d13-truth");
  await page.goto("/");
  const primary = page.locator(".workspace-main");
  await expect(primary).toContainText("评估时间已过期");
  await expect(primary).not.toContainText("下次评估 2026-08-09 13:00");
  await expect(page.locator("[data-ui='validation']")).toContainText("概率质量证据不足，方向指标仅作样本记录");
  await expect(page.locator("[data-ui='validation']")).not.toContainText("80.0%");
  await expect(page.locator("[data-ui='exclusion-reasons']")).toContainText("排除原因");
  await expect(page.locator("[data-ui='validation']")).toContainText("排除 40（71.4%）");
  const leagues = page.locator("[data-ui='league-performance']");
  await expect(leagues).toContainText("挪威超");
  await expect(leagues).toContainText("赛事名称待解析");
  await expect(leagues).not.toContainText("ID: 999");
  await expect(leagues).toContainText("国家联赛 2 · 杯赛 / 其他赛事 0（运行白名单 13）");
  await expect(leagues).not.toContainText("可用 80.0%");
  const modelSummary = page.locator(".model-lab-grid > div").nth(1);
  await expect(modelSummary.locator("strong")).toHaveText("证据不足");
  await expect(modelSummary).toContainText("让球：证据不足；大小球：证据不足");
  const scoreline = page.locator("[data-ui='scoreline-top3']");
  await expect(scoreline.locator(".workspace-section-heading")).toContainText("比分参考");
  await expect(scoreline.locator(".workspace-section-heading")).not.toContainText("10,000 次既有模拟");
  await expect(primary).toContainText("额度未读取（只读页面不查询 Provider）");
  await expect(page.locator(".sidebar-health")).toContainText("系统 / 数据健康");
  await expect(page.locator(".sidebar-health")).toContainText("Provider 额度读取");
  await expect(page.getByLabel("工作台日期")).toHaveAttribute("type", "text");
  await expect(page.getByLabel("工作台日期")).toHaveValue("2026-08-09");
  const publicCopy = await page.locator(".workspace-main").evaluate((element) => {
    const copy = element.cloneNode(true) as HTMLElement;
    copy.querySelectorAll("details").forEach((details) => details.remove());
    return copy.innerText;
  });
  expect(publicCopy).not.toMatch(/\b(?:ADVISORY|MARKET_NOT_READY|IDENTITY_NOT_READY|UNKNOWN)\b/);
});

test("D14 collection assessment, prior-only model and football-day truth stay explicit", async ({ page }) => {
  await installWorkspace(page, "collection-unassessed");
  await page.goto("/");
  const inspector = page.locator("[data-ui='match-inspector']");
  await expect(inspector.locator("[data-risk-axis='COLLECTION_RISK']")).toContainText("未评估");
  await expect(inspector.locator("[data-risk-axis='COLLECTION_RISK']")).not.toContainText("正常");
  await expect(page.locator("[data-ui='football-day-boundary']")).toContainText("08-09 12:00 至 08-10 12:00（不含）");

  await installWorkspace(page, "baseline-prior");
  await page.reload();
  await expect(page.locator("[data-ui='match-inspector']")).toContainText("仅先验");
  await expect(page.locator("[data-ui='model-lab']")).toContainText("仅先验");
  await expect(page.locator("[data-ui='scoreline-context']")).toContainText("模型状态");
  await expect(page.locator("[data-ui='scoreline-context']")).toContainText("仅先验");
});

test("D14 homogeneous Attention collapses to one expandable aggregate", async ({ page }) => {
  await installWorkspace(page, "attention-homogeneous");
  await page.goto("/");
  const attention = page.locator("[data-ui='attention']");
  await expect(attention.locator("[data-ui='attention-aggregate']")).toHaveCount(1);
  await expect(attention.locator(".attention-row")).toHaveCount(1);
  await expect(attention).not.toContainText("暂无关注项");
  await attention.locator("[data-ui='attention-aggregate']").click();
  await expect(attention.locator(".attention-row")).toHaveCount(3);
  await expect(attention.getByRole("button", { name: "收起" })).toBeVisible();
});

test("D15 repeated Attention blockers default to two expandable summaries", async ({ page }) => {
  await installWorkspace(page, "attention-repeated-groups");
  await page.goto("/");
  const attention = page.locator("[data-ui='attention']");
  await expect(attention.locator("[data-ui='attention-aggregate']")).toHaveCount(2);
  await expect(attention.locator(".attention-row")).toHaveCount(2);
  await expect(attention).toContainText("2 组 · 6 场");
  await attention.locator("[data-ui='attention-aggregate']").first().click();
  await expect(attention.locator(".attention-row")).toHaveCount(3);
  await attention.locator("[data-ui='attention-aggregate']").click();
  await expect(attention.locator(".attention-row")).toHaveCount(6);
});

test("D15 price-only movement exposes exact label, deltas and quote terminology", async ({ page }) => {
  await installWorkspace(page, "layout");
  await page.goto("/");
  const card = page.locator("[data-market='ASIAN_HANDICAP']");
  await expect(card).toContainText("赔率变化");
  await expect(card).not.toContainText("变化盘口变化");
  await expect(card.locator("[data-ui='movement-evidence']")).toContainText("盘口 -0.25 → -0.25（Δ 0）");
  await expect(card.locator("[data-ui='movement-evidence']")).toContainText("主队赔率中位数");
  await expect(card).toContainText("2 个快照 · 8 组机构双边报价（16 条单边报价）");
  await expect(card).not.toContainText("次观测");
});

test("D15 stale Market Memory has one fail-closed public readiness authority", async ({ page }) => {
  await installWorkspace(page, "market-stale");
  await page.goto("/");
  const card = page.locator("[data-market='ASIAN_HANDICAP']");
  await expect(card).toHaveAttribute("data-market-evidence-status", "STALE");
  await expect(card).toContainText("市场证据：已过期");
  await expect(card).toContainText("历史快照（已过期，不可用于当前模型比较）");
  await expect(card).not.toContainText("市场证据：就绪");
  await expect(page.locator("[data-ui='match-inspector']")).toContainText("市场证据状态已过期");
  await expect(page.locator("[data-ui='model-lab']")).toContainText("模型比较状态");
  await expect(page.locator("[data-ui='model-lab']")).toContainText("市场证据未就绪");
});

test("D15 scoreline context uses three structural labels", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  const context = page.locator("[data-ui='scoreline-context']");
  for (const label of ["模型状态", "比赛就绪", "阻塞原因"]) await expect(context).toContainText(label);
  await expect(context.locator("span")).toHaveCount(3);
});

test("D14 canonical Chinese competition names keep tournaments separate", async ({ page }) => {
  await installWorkspace(page, "tournament-truth");
  await page.goto("/");
  const publicCopy = await page.locator("[data-ui='league-performance']").evaluate((element) => {
    const copy = element.cloneNode(true) as HTMLElement;
    copy.querySelectorAll("details").forEach((details) => details.remove());
    return copy.innerText;
  });
  expect(publicCopy).toContain("英超");
  expect(publicCopy).toContain("杯赛 / 其他赛事");
  expect(publicCopy).toContain("世界杯");
  expect(publicCopy).not.toMatch(/Premier League|World Cup|world_cup_2026/);
});

test("all seven intelligence states and the exact four risk axes render without semantic promotion", async ({ page }) => {
  await installWorkspace(page, "seven-states");
  await page.goto("/");
  await page.getByRole("button", { name: "查看全部（7）" }).click();
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

for (const [scenario, expected, canonical] of [
  ["lineup-too-early", "当前尚不应提供", "NOT_EXPECTED_YET"],
  ["lineup-absent", "来源数据为空", "PROVIDER_EMPTY"],
  ["injuries-stale", "伤停信息已过期", "INJURIES_STALE"],
  ["market-stale", "已过期", "STALE"],
  ["collection-incident", "额度受保护（降级）", "COLLECTION_PROVIDER_INCIDENT"],
  ["model-not-ready", "模型模拟未就绪", "MODEL_SIMULATION_NOT_READY"],
  ["validation-insufficient", "证据不足", "INSUFFICIENT"],
  ["validation-metadata-missing", "技术详情", "CHECKPOINT_METADATA_NOT_AVAILABLE"],
] as const) {
  test(`truth scenario ${scenario} stays explicit`, async ({ page }) => {
    await installWorkspace(page, scenario);
    await page.goto("/");
    await expect(page.locator(".workspace-main")).toContainText(expected);
    await expect(page.locator(".workspace-main")).toContainText(canonical);
  });
}

test("SAMPLE_BUILDING, external NOT_CONNECTED, replay evidence and replay gaps are explicit", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  await expect(page.locator("[data-ui='validation']")).toContainText("SAMPLE_BUILDING");
  await expect(page.locator("[data-ui='validation']")).toContainText("NOT_DEFINED");
  await expect(page.locator("[data-ui='external-intelligence'] strong")).toHaveCount(4);
  await expect(page.locator("[data-ui='external-intelligence']")).toContainText("NOT_CONNECTED");
  await expect(page.locator("[data-ui='external-intelligence'] article").first()).toHaveAttribute("data-affects-match-readiness", "false");
  await expect(page.locator("[data-ui='history-replay']")).toContainText("AVAILABLE_WITH_GAPS");
  await expect(page.locator("[data-ui='history-replay']")).toContainText("MISSING_OUTCOMES_FOR_2_FIXTURES");
  await expect(page.locator("[data-ui='history-replay']")).toContainText("哈希检查1");
});

test("empty day is explicit and never fabricates a match", async ({ page }) => {
  await installWorkspace(page, "empty");
  await page.goto("/");
  await expect(page.locator("[data-ui='match-board']")).toContainText("今日暂无比赛");
  await expect(page.locator(".match-board-row")).toHaveCount(0);
  await expect(page.locator("[data-ui='match-inspector']")).toContainText("尚未选择比赛");
});

test("public copy excludes forbidden decision and commercial semantics", async ({ page }) => {
  await installWorkspace(page);
  await page.goto("/");
  const body = page.locator("body");
  for (const forbidden of ["CLV", "ROI", "expected_value", "value_score", "opportunity_score", "market_pick", "anonymous_live_odds_benchmark", "Recommendation Board", "Boss Decision Console"]) await expect(body).not.toContainText(forbidden);
  await expect(body).toContainText("优先检查模型校准、特征时效、盘口身份和数据质量");
  await expect(body).toContainText("正式建议保持关闭");
});

test("1536x1024 owner viewport preserves complete primary document flow", async ({ page }) => {
  await installWorkspace(page, "layout");
  await page.goto("/");
  await expect(page.locator(".match-board-row")).toHaveCount(6);
  await expect(page.locator("[data-ui='attention'] .attention-row")).toHaveCount(5);
  const fifthAttentionBox = await page.locator("[data-ui='attention'] .attention-row").nth(4).boundingBox();
  const attentionTableBox = await page.locator("[data-ui='attention-feed']").boundingBox();
  expect(fifthAttentionBox!.y + fifthAttentionBox!.height).toBeLessThanOrEqual(attentionTableBox!.y + attentionTableBox!.height + 1);
  await expect(page.locator("[data-ui='attention-aggregate']")).toHaveCount(1);
  for (const surface of ["attention", "market-radar", "external-intelligence", "match-board", "match-inspector", "model-lab", "scoreline-top3", "validation", "league-performance"]) {
    const box = await page.locator(`[data-ui='${surface}']`).boundingBox();
    expect(box, surface).not.toBeNull();
    expect(box!.width, surface).toBeGreaterThan(0);
    expect(box!.height, surface).toBeGreaterThan(0);
  }
  const primaryText = await page.locator(".workspace-grid").evaluate((element) => {
    const copy = element.cloneNode(true) as HTMLElement;
    copy.querySelectorAll("details").forEach((details) => details.remove());
    return copy.innerText;
  });
  expect(primaryText).not.toMatch(/(?:COLLECTION|DATA|MODEL|MARKET)_[A-Z_]+/);
  await expectDeterministicScreenshot(page);
});

for (const viewport of [{ width: 1280, height: 720 }, { width: 1280, height: 800 }, { width: 1366, height: 768 }, { width: 1440, height: 900 }, { width: 1512, height: 982 }, { width: 1536, height: 1024 }, { width: 1920, height: 1080 }]) {
  test(`D13 responsive acceptance ${viewport.width}x${viewport.height}`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    await installWorkspace(page, "layout");
    await page.goto("/");
    await page.addStyleTag({ content: "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}html{scroll-behavior:auto!important}" });
    const geometry = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }));
    expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.clientWidth);
    await expect(page.locator("[data-market='ASIAN_HANDICAP'] [data-price-side='HOME'] strong")).toHaveText("1.89");
    await expect(page.locator("[data-ui='market-radar']")).toContainText("赔率变化");
    await expect(page.locator("[data-ui='attention']")).toContainText("数据字段已过期");
    await expect(page.locator("[data-ui='header-context']")).toContainText("系统 当日阻塞");
    const columns = await page.locator(".workspace-grid").evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length);
    expect(columns).toBe(viewport.width <= 1512 ? 2 : 3);
    const fontSizes = await page.evaluate(() => Object.fromEntries(Object.entries({
      heading: ".workspace-section-heading h2",
      primaryRow: ".match-board-row > strong",
      primaryValue: ".workspace-key-value strong",
      leagueRow: ".league-table-row",
      secondary: ".workspace-section-heading span",
    }).map(([name, selector]) => [name, Number.parseFloat(getComputedStyle(document.querySelector(selector)!).fontSize)])));
    expect(fontSizes.heading).toBeGreaterThanOrEqual(16);
    for (const name of ["primaryRow", "primaryValue", "leagueRow"] as const) expect(fontSizes[name]).toBeGreaterThanOrEqual(12);
    expect(fontSizes.secondary).toBeGreaterThanOrEqual(10);
    await expect(page.locator("[data-ui='attention']")).toBeVisible();
    await expect(page.locator("[data-ui='match-board']")).toBeVisible();
    const directPanels = await page.locator(".workspace-grid > .workspace-panel, .workspace-grid > .selected-column").evaluateAll((elements) => elements.map((element) => {
      const box = element.getBoundingClientRect();
      return { left: box.left, right: box.right, top: box.top, bottom: box.bottom };
    }));
    for (let left = 0; left < directPanels.length; left += 1) for (let right = left + 1; right < directPanels.length; right += 1) {
      const a = directPanels[left]; const b = directPanels[right];
      const overlapWidth = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const overlapHeight = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      expect(overlapWidth > 1 && overlapHeight > 1, `panels ${left}/${right} overlap`).toBe(false);
    }
    for (const selector of [".attention-table", ".match-board-body", ".league-table"]) {
      const scroll = await page.locator(selector).evaluate((element) => ({ clientHeight: element.clientHeight, scrollHeight: element.scrollHeight, overflowY: getComputedStyle(element).overflowY }));
      expect(["auto", "scroll"]).toContain(scroll.overflowY);
      expect(scroll.clientHeight).toBeGreaterThan(0);
    }
    await page.locator("[data-ui='validation']").scrollIntoViewIfNeeded();
    const stickyClearance = await page.evaluate(() => {
      const header = document.querySelector(".workspace-topbar")!.getBoundingClientRect();
      const panel = document.querySelector("[data-ui='validation']")!.getBoundingClientRect();
      return { headerBottom: header.bottom, panelTop: panel.top, sticky: getComputedStyle(document.querySelector(".workspace-topbar")!).position === "sticky" };
    });
    if (stickyClearance.sticky) expect(stickyClearance.panelTop).toBeGreaterThanOrEqual(stickyClearance.headerBottom - 1);
    for (const [position, ratio] of [["top", 0], ["middle", 0.5], ["bottom", 1]] as const) {
      await page.evaluate((value) => window.scrollTo(0, (document.documentElement.scrollHeight - innerHeight) * value), ratio);
      await page.screenshot({ animations: "disabled", path: testInfo.outputPath(`dashboard-${viewport.width}x${viewport.height}-${position}.png`) });
    }
    await page.evaluate(() => window.scrollTo(0, 0));
    await expectDeterministicScreenshot(page);
  });
}

test("endpoint failure stays fail-closed without legacy fallback", async ({ page }) => {
  await page.route("**/v1/dashboard/intelligence-workspace?**", (route) => route.fulfill({ status: 503, json: { code: "SYSTEM_DEGRADED" } }));
  await page.goto("/");
  await expect(page.locator(".workspace-load-state--error")).toContainText("统一情报工作台暂不可用");
  await expect(page.locator(".workspace-load-state--error")).toContainText("不会回退旧 Dashboard，也不会填充合成数据");
});
