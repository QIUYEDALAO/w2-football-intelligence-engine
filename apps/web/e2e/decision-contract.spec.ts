import { expect, test, type Page, type Route } from "@playwright/test";

type Scenario =
  | "READY"
  | "STALE"
  | "BLOCKED"
  | "INCOMPLETE"
  | "CHECKPOINT_MISSING";

const scenarioContract = {
  READY: {
    decision: "RECOMMEND",
    data: "READY",
    reason: null,
    tierLabel: "正式可锁",
  },
  STALE: {
    decision: "WATCH",
    data: "STALE",
    reason: "DATA_STALE_ODDS",
    tierLabel: "观察",
  },
  BLOCKED: {
    decision: "NOT_READY",
    data: "BLOCKED",
    reason: "CONTRACT_BLOCKED_BY_DATA_STATUS",
    tierLabel: "未就绪",
  },
  INCOMPLETE: {
    decision: "NOT_READY",
    data: "BLOCKED",
    reason: "MARKET_INCOMPLETE",
    tierLabel: "未就绪",
  },
  CHECKPOINT_MISSING: {
    decision: "NOT_READY",
    data: "BLOCKED",
    reason: "FROZEN_ARTIFACT_MISSING",
    tierLabel: "未就绪",
  },
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
        last_known_odds: {},
        pick: {
          market: "ASIAN_HANDICAP",
          selection: "HOME_AH",
          line: "-0.5",
          odds: "1.91",
        },
        probability_source: "MARKET_DEVIG",
        model_market_divergence: {
          status: "READY",
          direction_allowed: true,
          magnitude: 0.08,
        },
        scoreline_picks: [
          {
            scoreline: "1-0",
            home_goals: 1,
            away_goals: 0,
            probability: 0.12,
            probability_label: "12%",
          },
          {
            scoreline: "1-1",
            home_goals: 1,
            away_goals: 1,
            probability: 0.11,
            probability_label: "11%",
          },
          {
            scoreline: "2-0",
            home_goals: 2,
            away_goals: 0,
            probability: 0.09,
            probability_label: "9%",
          },
        ],
        scoreline_reference: {
          source: "formal_simulation",
          label: "模拟比分参考",
          direction_top3: [
            {
              scoreline: "1-0",
              home_goals: 1,
              away_goals: 0,
              probability: 0.12,
              probability_label: "12%",
            },
            {
              scoreline: "2-0",
              home_goals: 2,
              away_goals: 0,
              probability: 0.09,
              probability_label: "9%",
            },
            {
              scoreline: "2-1",
              home_goals: 2,
              away_goals: 1,
              probability: 0.08,
              probability_label: "8%",
            },
          ],
        },
        scoreline_readiness: { status: "READY", source: "formal_simulation" },
        scoreline_simulations: 10000,
        diagnostics: {
          frozen_artifact_status:
            scenario === "CHECKPOINT_MISSING" ? "MISSING" : "VERIFIED",
        },
      },
    ],
  };
}

async function json(route: Route, body: unknown): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function installRoutes(
  page: Page,
  scenario: Scenario,
  readyCardCount = 1,
  scheduledWait = false,
): Promise<void> {
  const contract = scenarioContract[scenario];
  const dayViewPayload = dayView(scenario);
  if (scheduledWait) {
    dayViewPayload.cards[0].kickoff_utc = "2026-07-20T12:00:00Z";
    dayViewPayload.cards[0].next_eval_at = "2026-07-20T06:00:00Z";
    dayViewPayload.cards[0].reason_code = null;
    dayViewPayload.cards[0].non_pick = {
      reason_code: "DATA_STALE_ODDS",
      action: "WAIT_NEXT_REFRESH",
      next_eval_at: "2026-07-20T06:00:00Z",
    };
    dayViewPayload.cards[0].last_known_odds = {
      status: "REFERENCE_ONLY",
      captured_at: "2026-07-17T14:48:45Z",
      executable: false,
      bookmaker_count: 10,
      markets: {
        ah: {
          line: "-0.5",
          home_line: "-0.5",
          away_line: "+0.5",
          home_price: 1.82,
          away_price: 1.86,
        },
        ou: {
          line: "2.75",
          over_price: 1.91,
          under_price: 1.93,
        },
      },
    };
  }
  if (scenario === "READY" && readyCardCount > 1) {
    const template = dayViewPayload.cards[0];
    dayViewPayload.cards = Array.from(
      { length: readyCardCount },
      (_, index) => ({
        ...template,
        fixture_id: `fixture-ready-${index + 1}`,
        home_team_name: `READY Home ${index + 1}`,
        away_team_name: `READY Away ${index + 1}`,
      }),
    );
    dayViewPayload.counts.total = readyCardCount;
    dayViewPayload.counts.lock_eligible = readyCardCount;
    dayViewPayload.counts.recommend = readyCardCount;
    dayViewPayload.counts.ready = readyCardCount;
  }
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/meta.json") {
      return json(route, {
        web_git_sha: "e2e0001",
        release_id: "e2e",
        data_mode: "api",
      });
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
          pick: ready
            ? { market: "ASIAN_HANDICAP", selection: "HOME_AH" }
            : null,
          current_odds: ready ? { ah: { home_price: "1.91" } } : {},
          lock_eligible: ready,
          frozen_artifact_provenance:
            scenario === "CHECKPOINT_MISSING"
              ? { status: "BLOCKED", blockers: ["FROZEN_ARTIFACT_MISSING"] }
              : { status: "VERIFIED", artifact_hash: "a".repeat(64) },
        },
      });
    }
    return route.continue();
  });
}

test("READY renders the unified pick and verified analysis-card", async ({
  page,
}) => {
  await installRoutes(page, "READY");
  await page.goto("/");

  const row = page
    .locator("article.decision-row")
    .filter({ hasText: "READY Home" });
  await expect(row).toContainText("正式可锁");
  await expect(row).toContainText("1.91");
  await expect(row).toContainText("推荐盘口：让球 主 -0.5 @1.91");
  await expect(row).toContainText("推荐比分：1-0 · 2-0 · 2-1");
  await expect(row).not.toContainText("1万次模拟");
  await expect(page.locator(".boss-command-meta")).toContainText("已出推荐 1");
  await expect(page.locator(".boss-command-meta")).toContainText(
    "页面更新 18:00",
  );
  await expect(page.locator(".boss-command-meta")).toContainText(
    "赔率确认 17:55",
  );
  await expect(page.locator(".boss-command-meta")).toContainText(
    "下次采集 18:15",
  );
  await expect(page.locator(".boss-command-meta > span")).toHaveCount(6);
  const headerGeometry = await page.evaluate(() => {
    const view = document
      .querySelector(".boss-view-select")
      ?.getBoundingClientRect();
    const meta = document
      .querySelector(".boss-command-meta")
      ?.getBoundingClientRect();
    const release = document
      .querySelector(".boss-command-release")
      ?.getBoundingClientRect();
    const items = Array.from(
      document.querySelectorAll(".boss-command-meta > span"),
    );
    const firstItem = items[0]?.getBoundingClientRect();
    const lastItem = items[items.length - 1]?.getBoundingClientRect();
    const metaElement = document.querySelector(".boss-command-meta");
    return {
      viewRight: view?.right ?? 0,
      firstItemLeft: firstItem?.left ?? 0,
      lastItemRight: lastItem?.right ?? 0,
      releaseLeft: release?.left ?? 0,
      metaClientWidth: metaElement?.clientWidth ?? 0,
      metaScrollWidth: metaElement?.scrollWidth ?? 0,
    };
  });
  expect(headerGeometry.viewRight).toBeLessThanOrEqual(
    headerGeometry.firstItemLeft,
  );
  expect(headerGeometry.lastItemRight).toBeLessThanOrEqual(
    headerGeometry.releaseLeft,
  );
  expect(headerGeometry.metaScrollWidth).toBeLessThanOrEqual(
    headerGeometry.metaClientWidth,
  );
  const analysis = await page.evaluate(async () => {
    const response = await fetch("/v1/fixtures/fixture-ready/analysis-card");
    return response.json();
  });
  expect(analysis.card.decision_tier).toBe("RECOMMEND");
  expect(analysis.card.frozen_artifact_provenance.status).toBe("VERIFIED");
});

test("all qualifying recommendations remain visible without a top-three cap", async ({
  page,
}) => {
  await installRoutes(page, "READY", 4);
  await page.goto("/");

  await expect(
    page.locator("article.decision-row").filter({ hasText: "正式可锁" }),
  ).toHaveCount(4);
  await expect(page.locator(".boss-command-meta")).toContainText("已出推荐 4");
});

test("stored early odds remain visible as reference while waiting for the prematch refresh", async ({
  page,
}) => {
  await installRoutes(page, "STALE", 1, true);
  await page.goto("/");

  const row = page
    .locator("article.decision-row")
    .filter({ hasText: "STALE Home" });
  const visibleRow = row.locator(".decision-row-button");
  await expect(visibleRow).toContainText("缺临场赔率·14:00更新");
  await expect(visibleRow).toContainText(
    "暂无推荐比分：缺临场赔率，14:00刷新后再判断",
  );
  await expect(visibleRow).not.toContainText("1万次模拟");
  await expect(visibleRow).toContainText(
    "市场早盘（非推荐）：让球 主 -0.5 @1.82 / 客 +0.5 @1.86",
  );
  await expect(visibleRow).toContainText("已过期，仅参考");
  await expect(visibleRow).not.toContainText("数据陈旧");
  await expect(page.locator(".health-strip")).toContainText("缺少最新临场赔率");
  await expect(page.locator(".health-strip")).toContainText(
    "1 场当前只有过期早盘；14:00采集后重新判断能否形成推荐",
  );
  await expect(page.locator(".health-strip")).not.toContainText(
    "部分数据需处理",
  );
});

test("enabled leagues and club teams render localized Chinese names", async ({
  page,
}) => {
  await installRoutes(page, "STALE", 1, true);
  await page.route("**/v1/dashboard/day-view?**", async (route) => {
    const payload = dayView("STALE");
    payload.cards[0].competition_name = "Allsvenskan · Regular Season - 13";
    payload.cards[0].home_team_name = "IF Elfsborg";
    payload.cards[0].away_team_name = "Sirius";
    payload.cards[0].kickoff_utc = "2026-07-19T14:30:00Z";
    payload.cards[0].next_eval_at = "2026-07-19T08:30:00Z";
    await json(route, payload);
  });
  await page.goto("/");

  const row = page
    .locator("article.decision-row")
    .filter({ hasText: "埃尔夫斯堡 vs 天狼星" });
  await expect(row).toContainText("瑞典超");
  await expect(row).toContainText("22:30");
  await expect(row).not.toContainText("IF Elfsborg");
  await expect(row).not.toContainText("Allsvenskan");
});

test("post-match validation uses one canonical cohort at desktop and 824px", async ({
  page,
}) => {
  await installRoutes(page, "STALE", 1, true);
  await page.route("**/v1/dashboard/day-view?**", async (route) => {
    const payload = {
      ...dayView("STALE"),
      performance: {
        forward_ledger: {
          schema_version: "w2.forward_ledger_performance.v3",
          validation_fixture_count: 23,
          validation_settled_fixture_count: 23,
          canonical_settled_fixture_count: 16,
          canonical_excluded_count: 7,
          outcomes_canonical: {
            settled_sample_count: 16,
            hit_count: 11,
            miss_count: 3,
            push_count: 2,
            void_count: 0,
            hit_rate: 11 / 14,
          },
          performance_cohort: {
            validation_count: 23,
            processed_count: 23,
            eligible_count: 16,
            excluded_count: 7,
            recovered_count: 4,
            pending_count: 0,
            outcomes: {
              settled_sample_count: 16,
              decisive_count: 14,
              hit_count: 11,
              miss_count: 3,
              push_count: 2,
              void_count: 0,
              hit_rate: 11 / 14,
            },
            clv: {
              sample_count: 13,
              median_decimal: 0,
              positive_count: 2,
              negative_count: 2,
              push_count: 6,
              line_changed_count: 0,
            },
            by_league: [
              ["league-no", "挪威超", 7, 6, 1, 4, 1, 1, 0.8, 6],
              ["league-se", "瑞典超", 6, 4, 2, 3, 1, 0, 0.75, 4],
              ["169", "中超", 5, 1, 4, 0, 1, 0, 0, 1],
              ["serie-a", "意甲", 3, 3, 0, 3, 0, 0, 1, 1],
              ["world-cup", "世界杯", 2, 2, 0, 1, 0, 1, 1, 1],
            ].map(
              ([
                competitionId,
                league,
                processed,
                eligible,
                excluded,
                hit,
                miss,
                push,
                hitRate,
                clvSamples,
              ]) => ({
                competition_id: competitionId,
                league,
                processed_count: processed,
                eligible_count: eligible,
                excluded_count: excluded,
                decisive_count: Number(hit) + Number(miss),
                outcomes: {
                  settled_sample_count: eligible,
                  decisive_count: Number(hit) + Number(miss),
                  hit_count: hit,
                  miss_count: miss,
                  push_count: push,
                  void_count: 0,
                  hit_rate: hitRate,
                },
                clv: {
                  sample_count: clvSamples,
                  median_decimal: clvSamples ? 0 : null,
                  positive_count: 0,
                  negative_count: 0,
                  push_count: clvSamples,
                  line_changed_count: 0,
                },
                rate_status:
                  Number(hit) + Number(miss) >= 5
                    ? "AVAILABLE"
                    : "INSUFFICIENT",
              }),
            ),
            exclusions: Array.from({ length: 7 }, (_, index) => ({
              fixture_id: `excluded-${index}`,
              competition_id: index < 4 ? "169" : "legacy",
              league: index < 4 ? "中超" : "历史联赛",
              home_team_name: `主队 ${index + 1}`,
              away_team_name: `客队 ${index + 1}`,
              kickoff_utc: "2026-07-10T12:00:00Z",
              settlement_outcome: "LOSS",
              reason_code: "LEGACY_CAPTURE_LINK_MISSING",
              reason_label: "历史推荐与赛果身份链缺失",
            })),
            recoveries: Array.from({ length: 4 }, (_, index) => ({
              fixture_id: `recovered-${index}`,
              competition_id: index === 3 ? "world-cup" : "serie-a",
              league: index === 3 ? "世界杯" : "意甲",
              home_team_name: `恢复主队 ${index + 1}`,
              away_team_name: `恢复客队 ${index + 1}`,
              kickoff_utc: "2026-07-10T12:00:00Z",
              settlement_outcome: "WIN",
              recovery_code: "UNIQUE_LEGACY_CAPTURE_RECONSTRUCTED",
              recovery_label: "经唯一历史快照审计恢复",
            })),
            invariants: { status: "PASS" },
          },
        },
      },
    };
    await json(route, payload);
  });
  await page.goto("/");

  await expect(page.locator(".league-performance-table > div")).toHaveCount(6);
  await expect(page.locator(".league-performance-table")).toContainText("中超");
  await expect(page.locator(".verification-preview")).toContainText(
    "纳入统计 16 场",
  );
  await expect(page.locator(".verification-preview")).toContainText(
    "命中 11 · 未中 3 · 走水 2",
  );
  await expect(page.locator(".verification-preview")).toContainText(
    "有效输赢 14 场 · 命中率 79%",
  );
  await expect(page.locator(".verification-preview")).toContainText(
    "其中 4 场经唯一历史快照审计恢复",
  );
  await expect(page.locator(".verification-preview")).toContainText(
    "另有 7 场赛果已处理，因历史身份链缺失未纳入",
  );
  await expect(page.locator(".verification-preview")).not.toContainText(
    "全部已处理",
  );
  const csl = page
    .locator(".league-performance-table > div")
    .filter({ hasText: "中超" });
  await expect(csl).toContainText("1 场");
  await expect(csl).toContainText("0-1-0");
  await expect(csl).toContainText("样本不足（1）");
  await expect(csl).not.toContainText("0%");

  const exclusions = page.locator(".verification-exclusions summary");
  await exclusions.focus();
  await expect(exclusions).toBeFocused();
  await exclusions.press("Enter");
  await expect(
    page.locator(".verification-exclusion-list article"),
  ).toHaveCount(7);
  const recoveries = page.locator(".verification-recoveries summary");
  await recoveries.press("Enter");
  await expect(page.locator(".verification-recovery-list article")).toHaveCount(
    4,
  );

  await page.setViewportSize({ width: 824, height: 1100 });
  const hasHorizontalOverflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth >
      document.documentElement.clientWidth,
  );
  expect(hasHorizontalOverflow).toBe(false);
  const responsiveLabel = await csl
    .locator("span")
    .nth(1)
    .evaluate((element) => getComputedStyle(element, "::before").content);
  expect(responsiveLabel).toBe('"纳入统计"');
});

for (const scenario of [
  "STALE",
  "BLOCKED",
  "INCOMPLETE",
  "CHECKPOINT_MISSING",
] as const) {
  test(`${scenario} never renders current odds, pick, or recommendation`, async ({
    page,
  }) => {
    await installRoutes(page, scenario);
    await page.goto("/");

    const row = page
      .locator("article.decision-row")
      .filter({ hasText: `${scenario} Home` });
    await expect(row).toContainText(scenarioContract[scenario].tierLabel);
    await expect(row).not.toContainText("1.91");
    await expect(row).not.toContainText("正式可锁");
    await expect(page.locator(".boss-command-meta")).toContainText(
      "已出推荐 0",
    );
    const analysis = await page.evaluate(async (fixture) => {
      const response = await fetch(`/v1/fixtures/${fixture}/analysis-card`);
      return response.json();
    }, `fixture-${scenario.toLowerCase()}`);
    expect(analysis.card.pick).toBeNull();
    expect(analysis.card.current_odds).toEqual({});
    expect(analysis.card.lock_eligible).toBe(false);
  });
}
