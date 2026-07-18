import { expect, test, type Page, type Route } from "@playwright/test";

type Scenario = "READY" | "STALE" | "BLOCKED" | "INCOMPLETE" | "CHECKPOINT_MISSING";

const scenarioContract = {
  READY: { decision: "RECOMMEND", data: "READY", reason: null, tierLabel: "正式可锁" },
  STALE: { decision: "WATCH", data: "STALE", reason: "DATA_STALE_ODDS", tierLabel: "观察" },
  BLOCKED: { decision: "NOT_READY", data: "BLOCKED", reason: "CONTRACT_BLOCKED_BY_DATA_STATUS", tierLabel: "未就绪" },
  INCOMPLETE: { decision: "NOT_READY", data: "BLOCKED", reason: "MARKET_INCOMPLETE", tierLabel: "未就绪" },
  CHECKPOINT_MISSING: { decision: "NOT_READY", data: "BLOCKED", reason: "FROZEN_ARTIFACT_MISSING", tierLabel: "未就绪" },
} as const;

function dayView(scenario: Scenario) {
  const contract = scenarioContract[scenario];
  const ready = scenario === "READY";
  return {
    request_id: "e2e",
    generated_at: "2026-07-18T10:00:00Z",
    date: "2026-07-18",
    football_day: "2026-07-18",
    selected_football_day: "2026-07-18",
    environment: "staging",
    timezone: "Asia/Shanghai",
    window: "future",
    source: "frozen_authority",
    provider_calls: 0,
    db_writes: 0,
    counts: {
      total: 1,
      lock_eligible: ready ? 1 : 0,
      outcome_tracked: 0,
      legacy_fallback: 0,
      analysis_pick: 0,
      recommend: ready ? 1 : 0,
      watch: scenario === "STALE" ? 1 : 0,
      not_ready: ready || scenario === "STALE" ? 0 : 1,
      skip: 0,
      ready: ready ? 1 : 0,
      partial: 0,
      stale: scenario === "STALE" ? 1 : 0,
      blocked: !ready && scenario !== "STALE" ? 1 : 0,
    },
    freshness: {
      page_updated_at: "2026-07-18T10:00:00Z",
      odds_last_confirmed_at: "2026-07-18T09:55:00Z",
      last_refresh: "2026-07-18T10:00:00Z",
      next_refresh_tick: "2026-07-18T10:15:00Z",
      provider_budget_status: "PROTECTED",
      refreshing: false,
      staleness: {
        stale_cards: scenario === "STALE" ? 1 : 0,
        blocked_cards: !ready && scenario !== "STALE" ? 1 : 0,
        stale_or_blocked_cards: ready ? 0 : 1,
      },
    },
    cards: [
      {
        fixture_id: `fixture-${scenario.toLowerCase()}`,
        kickoff_utc: "2026-07-19T12:00:00Z",
        competition_id: "test-league",
        competition_name: "Contract League",
        home_team_name: `${scenario} Home`,
        away_team_name: `${scenario} Away`,
        status: "NS",
        source: "frozen_authority",
        decision_tier: contract.decision,
        data_status: contract.data,
        lifecycle_status: "DRAFT",
        outcome_tracked: ready,
        lock_eligible: ready,
        recommendation_id: "must-be-hidden-when-not-ready",
        reason_code: contract.reason,
        action: ready ? "KEEP_WATCHING" : "WAIT_NEXT_REFRESH",
        next_eval_at: "2026-07-18T10:15:00Z",
        missing_fields: scenario === "INCOMPLETE" ? ["quote_identity"] : [],
        stale_fields: scenario === "STALE" ? ["quote.captured_at"] : [],
        current_odds: {
          ah: {
            home_line: "-0.5",
            away_line: "+0.5",
            home_price: "1.91",
            away_price: "1.95",
          },
        },
        pick: {
          market: "ASIAN_HANDICAP",
          selection: "HOME_AH",
          line: "-0.5",
          odds: "1.91",
        },
        probability_source: "MARKET_DEVIG",
        model_market_divergence: { status: "READY", direction_allowed: true, magnitude: 0.08 },
        diagnostics: {
          frozen_artifact_status: scenario === "CHECKPOINT_MISSING" ? "MISSING" : "VERIFIED",
        },
      },
    ],
  };
}

async function json(route: Route, body: unknown): Promise<void> {
  await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
}

async function installRoutes(page: Page, scenario: Scenario, readyCardCount = 1): Promise<void> {
  const contract = scenarioContract[scenario];
  const dayViewPayload = dayView(scenario);
  if (scenario === "READY" && readyCardCount > 1) {
    const template = dayViewPayload.cards[0];
    dayViewPayload.cards = Array.from({ length: readyCardCount }, (_, index) => ({
      ...template,
      fixture_id: `fixture-ready-${index + 1}`,
      home_team_name: `READY Home ${index + 1}`,
      away_team_name: `READY Away ${index + 1}`,
    }));
    dayViewPayload.counts.total = readyCardCount;
    dayViewPayload.counts.lock_eligible = readyCardCount;
    dayViewPayload.counts.recommend = readyCardCount;
    dayViewPayload.counts.ready = readyCardCount;
  }
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/meta.json") {
      return json(route, { web_git_sha: "e2e0001", release_id: "e2e", data_mode: "api" });
    }
    if (url.pathname === "/v1/version") {
      return json(route, {
        service: "w2",
        environment: "staging",
        api_git_sha: "e2e0001",
        release_id: "e2e",
        data_profile: "real-db",
        data_source: "frozen_authority",
        database_ready: true,
        read_model_fixture_count: 1,
        matchday_card_count: 1,
        result_event_count: 0,
        generated_at: "2026-07-18T10:00:00Z",
      });
    }
    if (url.pathname === "/v1/formal/tracking/summary") {
      return json(route, null);
    }
    if (url.pathname === "/v1/dashboard/day-view") {
      return json(route, dayViewPayload);
    }
    if (url.pathname.includes("/analysis-card")) {
      const ready = scenario === "READY";
      return json(route, {
        fixture_id: `fixture-${scenario.toLowerCase()}`,
        card: {
          decision_tier: contract.decision,
          data_status: contract.data,
          pick: ready ? { market: "ASIAN_HANDICAP", selection: "HOME_AH" } : null,
          current_odds: ready ? { ah: { home_price: "1.91" } } : {},
          lock_eligible: ready,
          frozen_artifact_provenance: scenario === "CHECKPOINT_MISSING"
            ? { status: "BLOCKED", blockers: ["FROZEN_ARTIFACT_MISSING"] }
            : { status: "VERIFIED", artifact_hash: "a".repeat(64) },
        },
      });
    }
    return route.continue();
  });
}

test("READY renders the unified pick and verified analysis-card", async ({ page }) => {
  await installRoutes(page, "READY");
  await page.goto("/");

  const row = page.locator("article.decision-row").filter({ hasText: "READY Home" });
  await expect(row).toContainText("正式可锁");
  await expect(row).toContainText("1.91");
  await expect(page.locator(".boss-command-meta")).toContainText("已出推荐 1");
  await expect(page.locator(".boss-command-meta")).toContainText("页面更新 18:00");
  await expect(page.locator(".boss-command-meta")).toContainText("赔率确认 17:55");
  await expect(page.locator(".boss-command-meta")).toContainText("下次采集 18:15");
  const analysis = await page.evaluate(async () => {
    const response = await fetch("/v1/fixtures/fixture-ready/analysis-card");
    return response.json();
  });
  expect(analysis.card.decision_tier).toBe("RECOMMEND");
  expect(analysis.card.frozen_artifact_provenance.status).toBe("VERIFIED");
});

test("all qualifying recommendations remain visible without a top-three cap", async ({ page }) => {
  await installRoutes(page, "READY", 4);
  await page.goto("/");

  await expect(page.locator("article.decision-row").filter({ hasText: "正式可锁" })).toHaveCount(4);
  await expect(page.locator(".boss-command-meta")).toContainText("已出推荐 4");
});

for (const scenario of ["STALE", "BLOCKED", "INCOMPLETE", "CHECKPOINT_MISSING"] as const) {
  test(`${scenario} never renders current odds, pick, or recommendation`, async ({ page }) => {
    await installRoutes(page, scenario);
    await page.goto("/");

    const row = page.locator("article.decision-row").filter({ hasText: `${scenario} Home` });
    await expect(row).toContainText(scenarioContract[scenario].tierLabel);
    await expect(row).not.toContainText("1.91");
    await expect(row).not.toContainText("正式可锁");
    await expect(page.locator(".boss-command-meta")).toContainText("已出推荐 0");
    const analysis = await page.evaluate(async (fixture) => {
      const response = await fetch(`/v1/fixtures/${fixture}/analysis-card`);
      return response.json();
    }, `fixture-${scenario.toLowerCase()}`);
    expect(analysis.card.pick).toBeNull();
    expect(analysis.card.current_odds).toEqual({});
    expect(analysis.card.lock_eligible).toBe(false);
  });
}
