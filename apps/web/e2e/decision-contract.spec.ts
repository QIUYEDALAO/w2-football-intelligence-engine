import { expect, test, type Page, type Route } from "@playwright/test";

type Scenario = "READY" | "ANALYSIS_PICK" | "STALE" | "BLOCKED" | "INCOMPLETE" | "CHECKPOINT_MISSING";

const scenarioContract = {
  READY: { decision: "RECOMMEND", data: "READY", reason: null, tierLabel: "正式推荐（未开放）" },
  ANALYSIS_PICK: { decision: "ANALYSIS_PICK", data: "READY", reason: null, tierLabel: "分析参考" },
  STALE: { decision: "WATCH", data: "STALE", reason: "DATA_STALE_ODDS", tierLabel: "观察" },
  BLOCKED: { decision: "NOT_READY", data: "BLOCKED", reason: "CONTRACT_BLOCKED_BY_DATA_STATUS", tierLabel: "未就绪" },
  INCOMPLETE: { decision: "NOT_READY", data: "BLOCKED", reason: "MARKET_INCOMPLETE", tierLabel: "未就绪" },
  CHECKPOINT_MISSING: { decision: "NOT_READY", data: "BLOCKED", reason: "FROZEN_ARTIFACT_MISSING", tierLabel: "未就绪" },
} as const;

function dayView(scenario: Scenario) {
  const contract = scenarioContract[scenario];
  const ready = scenario === "READY";
  const analysisPick = scenario === "ANALYSIS_PICK";
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
      outcome_tracked: analysisPick ? 1 : 0,
      legacy_fallback: 0,
      analysis_pick: analysisPick ? 1 : 0,
      recommend: ready ? 1 : 0,
      watch: scenario === "STALE" ? 1 : 0,
      not_ready: ready || analysisPick || scenario === "STALE" ? 0 : 1,
      skip: 0,
      ready: ready || analysisPick ? 1 : 0,
      partial: 0,
      stale: scenario === "STALE" ? 1 : 0,
      blocked: !ready && !analysisPick && scenario !== "STALE" ? 1 : 0,
    },
    freshness: {
      last_refresh: "2026-07-18T10:00:00Z",
      next_refresh_tick: "2026-07-18T10:15:00Z",
      provider_budget_status: "PROTECTED",
      refreshing: false,
      staleness: {
        stale_cards: scenario === "STALE" ? 1 : 0,
        blocked_cards: !ready && !analysisPick && scenario !== "STALE" ? 1 : 0,
        stale_or_blocked_cards: ready || analysisPick ? 0 : 1,
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
        outcome_tracked: ready || analysisPick,
        lock_eligible: ready,
        recommendation_id: "must-be-hidden-when-not-ready",
        reason_code: contract.reason,
        action: ready || analysisPick ? "KEEP_WATCHING" : "WAIT_NEXT_REFRESH",
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

async function installRoutes(
  page: Page,
  scenario: Scenario,
  dayViewOverride?: ReturnType<typeof dayView>,
): Promise<void> {
  const contract = scenarioContract[scenario];
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
      return json(route, dayViewOverride ?? dayView(scenario));
    }
    if (url.pathname.includes("/analysis-card")) {
      const ready = scenario === "READY" || scenario === "ANALYSIS_PICK";
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

  const row = page.locator("article.attention-card").filter({ hasText: "READY Home" });
  await expect(row).toContainText("正式推荐（未开放）");
  await expect(row).toContainText("1.91");
  await expect(page.locator(".boss-command-meta")).toContainText("已出推荐 1");
  const analysis = await page.evaluate(async () => {
    const response = await fetch("/v1/fixtures/fixture-ready/analysis-card");
    return response.json();
  });
  expect(analysis.card.decision_tier).toBe("RECOMMEND");
  expect(analysis.card.frozen_artifact_provenance.status).toBe("VERIFIED");
});

test("ANALYSIS_PICK is visible as analysis but never as an open lock", async ({ page }) => {
  await installRoutes(page, "ANALYSIS_PICK");
  await page.goto("/");

  const card = page.locator("article.attention-card").filter({ hasText: "ANALYSIS_PICK Home" });
  await expect(card).toContainText("分析参考");
  await expect(card).toContainText("1.91");
  await expect(page.locator(".today-decision-summary")).toContainText("分析参考");
  await expect(page.locator("body")).not.toContainText("正式可锁");
});

test("all qualifying matches are shown without an arbitrary top-three cap", async ({ page }) => {
  const payload = dayView("ANALYSIS_PICK");
  payload.cards = Array.from({ length: 4 }, (_, index) => ({
    ...payload.cards[0],
    fixture_id: `fixture-analysis-${index + 1}`,
    home_team_name: `Qualified ${index + 1}`,
  }));
  payload.counts = { ...payload.counts, total: 4, analysis_pick: 4, outcome_tracked: 4 };
  await installRoutes(page, "ANALYSIS_PICK", payload);
  await page.goto("/");

  await expect(page.locator("article.attention-card")).toHaveCount(4);
  await expect(page.locator(".attention-board > header")).toContainText("4 场");
});

for (const scenario of ["STALE", "BLOCKED", "INCOMPLETE", "CHECKPOINT_MISSING"] as const) {
  test(`${scenario} never renders current odds, pick, or recommendation`, async ({ page }) => {
    await installRoutes(page, scenario);
    await page.goto("/");

    const row = page.locator("article.technical-schedule-row").filter({ hasText: `${scenario} Home` });
    await expect(row).toContainText(scenarioContract[scenario].tierLabel);
    await expect(row).not.toContainText("1.91");
    await expect(row).not.toContainText("正式推荐（未开放）");
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

test("empty match window explains that there is no advice", async ({ page }) => {
  const empty = dayView("STALE");
  empty.cards = [];
  empty.counts = { ...empty.counts, total: 0, watch: 0, stale: 0 };
  await installRoutes(page, "STALE", empty);
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "今天暂无可执行建议" })).toBeVisible();
  await expect(page.getByText("当前没有满足完整数据与决策条件的比赛")).toBeVisible();
  await expect(page.getByText("验证数据正在同步")).toBeVisible();
});

test("mobile layout fits the viewport and technical details are keyboard operable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installRoutes(page, "STALE");
  await page.goto("/");

  const noHorizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
  expect(noHorizontalOverflow).toBe(true);
  const summary = page.locator(".technical-details > summary");
  await summary.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".technical-details")).toHaveAttribute("open", "");
});
