import { expect, test, type Page, type Route } from "@playwright/test";
import { kickoffPresentation } from "../src/lib/matchTime";

type Scenario =
  | "READY"
  | "STALE"
  | "BLOCKED"
  | "INCOMPLETE"
  | "CHECKPOINT_MISSING";

const scenarioContract = {
  READY: {
    decision: "ANALYSIS_PICK",
    data: "READY",
    reason: null,
    tierLabel: "分析参考",
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
      lock_eligible: 0,
      outcome_tracked: 0,
      legacy_fallback: 0,
      analysis_pick: ready ? 1 : 0,
      recommend: 0,
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
        lock_eligible: false,
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
          scoreline_projection: {
            schema_version: "w2.scoreline_projection.v1",
            status: "READY",
            simulation_method: "seeded_joint_score_sampling",
            simulations_requested: 10000,
            simulations_completed: 10000,
            seed: 370,
            consistent_sample_count: 6417,
            consistent_sample_rate: 0.6417,
            consistency_status: "PASS",
            decision_hash: `hash-${scenario}`,
            top3: [
              {
                scoreline: "1-0",
                home_goals: 1,
                away_goals: 0,
                sample_count: 1130,
                unconditional_probability: 0.113,
                conditional_probability: 0.1761,
                probability: 0.113,
                probability_label: "11.3%",
              },
              {
                scoreline: "2-0",
                home_goals: 2,
                away_goals: 0,
                sample_count: 980,
                unconditional_probability: 0.098,
                conditional_probability: 0.1527,
                probability: 0.098,
                probability_label: "9.8%",
              },
              {
                scoreline: "2-1",
                home_goals: 2,
                away_goals: 1,
                sample_count: 870,
                unconditional_probability: 0.087,
                conditional_probability: 0.1356,
                probability: 0.087,
                probability_label: "8.7%",
              },
            ],
          },
        },
        scoreline_readiness: { status: "READY", source: "formal_simulation" },
        scoreline_simulations: 10000,
        diagnostics: {
          frozen_artifact_status:
            scenario === "CHECKPOINT_MISSING" ? "MISSING" : "VERIFIED",
        },
        ...(ready ? { recommendation_decision_v3: {
          schema_version: "w2.recommendation_decision.v3",
          outcome: "ANALYSIS_PICK",
          reason: {
            code: "ANALYSIS_ONLY",
            message: "当前仅提供分析参考",
          },
          next_action: "MONITOR",
          selected_candidate: {
            market: "ASIAN_HANDICAP",
            selection: "HOME",
            line: "-0.5",
            odds: null,
          },
          evaluated_candidate: {
            analysis_evidence: {
              comparison: {
                probability_delta: 0.08,
                status: "READY",
              },
              market_probability: {
                devig: { HOME: 0.52, AWAY: 0.48 },
              },
              model_probability: {
                calibration_status: "BASELINE_PRIOR",
                effective_probability: 0.6,
                expected_value: 0.146,
                ev_se: 0.04,
                model_version: "w2.formal.exact_dc_poisson.v1",
              },
              quote_identity: {
                bookmaker_id: "32",
                captured_at: "2026-07-18T09:55:00Z",
                identity_status: "COMPLETE",
                quotes: {
                  home: {
                    bookmaker_name: "Betano",
                    captured_at: "2026-07-18T09:55:00Z",
                    decimal_odds: "1.91",
                    line: "-0.5",
                    selection: "HOME",
                  },
                },
              },
            },
          },
          statuses: {},
          warnings: [],
          audit_refs: {},
          decision_hash: `hash-${scenario}`,
        } } : {}),
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
    dayViewPayload.counts.lock_eligible = 0;
    dayViewPayload.counts.analysis_pick = readyCardCount;
    dayViewPayload.counts.recommend = 0;
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
          lock_eligible: false,
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
    .locator("[data-fixture-id='fixture-ready']")
    .filter({ hasText: "READY Home" });
  await expect(row).toContainText("分析参考");
  await expect(row).toContainText("1.91");
  await expect(row).toContainText("让球 · 主队 -0.5 @1.91");
  await expect(row).toContainText("模型比分：1-0 · 2-0 · 2-1");
  await expect(row).not.toContainText("1万次模拟");
  await expect(page.locator("[data-ui='scoreline-top3-panel']")).toContainText(
    "10,000 次模拟",
  );
  await expect(page.locator("[data-ui='scoreline-top3-panel']")).toContainText(
    "一致样本 6,417 / 10,000",
  );
  const selected = page.locator("[data-ui='selected-match-panel']");
  await expect(selected).toContainText("Betano");
  await expect(selected).toContainText("模型概率60.0%");
  await expect(selected).toContainText("市场概率52.0%");
  await expect(selected).toContainText("概率差+0.080");
  await expect(selected).toContainText("EV+0.146");
  await expect(selected).toContainText("不确定性0.040");
  await expect(page.locator("[data-ui='command-header']")).toContainText("分析建议 1");
  await expect(page.locator("[data-ui='command-header']")).toContainText(
    "页面更新 18:00",
  );
  await expect(page.locator("[data-ui='command-header']")).toContainText(
    "全局最近赔率 17:55",
  );
  await expect(page.locator("[data-ui='command-header']")).toContainText(
    "下次采集 18:15",
  );
  await expect(page.locator(".d2-command-metrics > span")).toHaveCount(6);
  const headerGeometry = await page.evaluate(() => {
    const view = document
      .querySelector(".d2-console-badge")
      ?.getBoundingClientRect();
    const meta = document
      .querySelector(".d2-command-metrics")
      ?.getBoundingClientRect();
    const release = document
      .querySelector(".d2-release")
      ?.getBoundingClientRect();
    const items = Array.from(
      document.querySelectorAll(".d2-command-metrics > span"),
    );
    const firstItem = items[0]?.getBoundingClientRect();
    const lastItem = items[items.length - 1]?.getBoundingClientRect();
    const metaElement = document.querySelector(".d2-command-metrics");
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
  expect(analysis.card.decision_tier).toBe("ANALYSIS_PICK");
  expect(analysis.card.frozen_artifact_provenance.status).toBe("VERIFIED");
});

test("all qualifying recommendations remain visible without a top-three cap", async ({
  page,
}) => {
  await installRoutes(page, "READY", 5);
  await page.goto("/");

  await expect(
    page.locator("[data-fixture-id]").filter({ hasText: "分析参考" }),
  ).toHaveCount(5);
  await expect(page.locator("[data-ui='command-header']")).toContainText("分析建议 5");
});

test("30 fixtures remain reachable through the desktop schedule viewport", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1512, height: 900 });
  await installRoutes(page, "READY", 30);
  await page.goto("/");

  const rows = page.locator("[data-fixture-id]");
  await expect(rows).toHaveCount(30);
  const board = page.locator("[data-ui='schedule-scroller']");
  const geometry = await board.evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
  }));
  expect(geometry.scrollHeight).toBeGreaterThan(geometry.clientHeight);

  const last = rows.filter({ hasText: "READY Home 30" });
  await last.scrollIntoViewIfNeeded();
  await last.locator("button").click();
  await expect(last).toHaveClass(/is-selected/);
  await expect(page.locator("[data-ui='selected-match-panel']")).toContainText(
    "READY Home 30",
  );
  await expect(page.locator(".d2-date-header")).toContainText("30场");
});

test("15 fixtures use natural document scrolling on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installRoutes(page, "READY", 15);
  await page.goto("/");

  await expect(page.locator("[data-fixture-id]")).toHaveCount(15);
  const geometry = await page.locator("[data-ui='schedule-scroller']").evaluate((element) => ({
    overflowY: getComputedStyle(element).overflowY,
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
  }));
  expect(geometry.overflowY).toBe("visible");
  expect(geometry.clientHeight).toBe(geometry.scrollHeight);
  await page
    .locator("[data-fixture-id]")
    .filter({ hasText: "READY Home 15" })
    .scrollIntoViewIfNeeded();
});

test("Shanghai date-first clock advances and handles year boundary and match states", async ({
  page,
}) => {
  await page.clock.install({ time: new Date("2026-12-31T12:00:00Z") });
  await installRoutes(page, "STALE");
  await page.route("**/v1/dashboard/day-view?**", async (route) => {
    const payload = dayView("STALE");
    const template = payload.cards[0];
    payload.cards = [
      {
        ...template,
        fixture_id: "fixture-today",
        home_team_name: "Today Home",
        away_team_name: "Today Away",
        kickoff_utc: "2026-12-31T12:45:00Z",
      },
      {
        ...template,
        fixture_id: "fixture-tomorrow",
        home_team_name: "Tomorrow Home",
        away_team_name: "Tomorrow Away",
        kickoff_utc: "2027-01-01T00:30:00Z",
      },
      {
        ...template,
        fixture_id: "fixture-live",
        home_team_name: "Live Home",
        away_team_name: "Live Away",
        kickoff_utc: "2026-12-31T10:57:00Z",
        status: "LIVE",
      },
      {
        ...template,
        fixture_id: "fixture-finished",
        home_team_name: "Finished Home",
        away_team_name: "Finished Away",
        kickoff_utc: "2026-12-30T12:00:00Z",
        status: "FT",
      },
    ];
    payload.counts.total = payload.cards.length;
    await json(route, payload);
  });
  await page.goto("/");

  const today = page.locator("[data-fixture-id]").filter({ hasText: "Today Home" });
  await expect(today).toContainText("今天");
  await expect(today).toContainText("20:45");
  await expect(today).toContainText("还有 45 分钟");
  await page.clock.fastForward(60_000);
  await expect(today).toContainText("还有 44 分钟");

  const tomorrow = page
    .locator("[data-fixture-id]")
    .filter({ hasText: "Tomorrow Home" });
  await expect(tomorrow).toContainText("明天");
  await expect(tomorrow).toContainText("08:30");
  await expect(tomorrow).toContainText("01-01 周五");
  await expect(
    page.locator("[data-fixture-id]").filter({ hasText: "Live Home" }),
  ).toContainText("进行中 64′");
  expect(
    kickoffPresentation(
      { kickoff_utc: "2026-12-30T12:00:00Z", status: "FT" },
      new Date("2026-12-31T12:01:00Z"),
    ),
  ).toEqual({ primary: "完场", secondary: "12-30 20:00" });
  expect(
    kickoffPresentation(
      { kickoff_utc: "invalid-time", status: "NS" },
      new Date("2026-12-31T12:01:00Z"),
    ),
  ).toEqual({ primary: "时间待定", secondary: "无有效时间" });
});

test("stored early odds remain visible as reference while waiting for the prematch refresh", async ({
  page,
}) => {
  await installRoutes(page, "STALE", 1, true);
  await page.goto("/");

  const row = page
    .locator("[data-fixture-id]")
    .filter({ hasText: "STALE Home" });
  await expect(row).toContainText("赔率待更新");
  await expect(row).toContainText("DATA_STALE_ODDS");
  await expect(row).toContainText("观察");
  await expect(row).not.toContainText("1.82");
  await expect(row).not.toContainText("1万次模拟");
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
    .locator("[data-fixture-id]")
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
          validation_fixture_count: 26,
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
            validation_count: 26,
            processed_count: 23,
            eligible_count: 16,
            excluded_count: 7,
            recovered_count: 4,
            pending_count: 3,
            integrity_status: "PASS",
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
              sample_count: 3,
              candidate_count: 16,
              missing_count: 13,
              median_decimal: 0,
              positive_count: 1,
              negative_count: 1,
              push_count: 1,
              line_changed_count: 0,
              stale_closing_count: 8,
              insufficient_snapshot_count: 4,
            },
            by_league: [
              ["league-no", "挪威超", 7, 6, 1, 4, 1, 1, 0.8, 1, 0.04],
              ["league-se", "瑞典超", 6, 4, 2, 3, 1, 0, 0.75, 1, -0.02],
              ["169", "中超", 5, 1, 4, 0, 1, 0, 0, 1, 0],
              ["serie-a", "意甲", 3, 3, 0, 3, 0, 0, 1, 0, null],
              ["world-cup", "世界杯", 2, 2, 0, 1, 0, 1, 1, 0, null],
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
                clvMedian,
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
                  candidate_count: eligible,
                  missing_count: Number(eligible) - Number(clvSamples),
                  median_decimal: clvMedian,
                  positive_count: Number(clvMedian) > 0 ? 1 : 0,
                  negative_count: Number(clvMedian) < 0 ? 1 : 0,
                  push_count: clvMedian === 0 ? 1 : 0,
                  line_changed_count: 0,
                  stale_closing_count: 0,
                  insufficient_snapshot_count: 0,
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

  await expect(page.locator(".d2-league-table > div")).toHaveCount(6);
  await expect(page.locator(".d2-league-table")).toContainText("中超");
  await expect(page.locator("[data-ui='forward-validation-panel']")).toContainText(
    "纳入统计 16 场",
  );
  await expect(page.locator("[data-ui='forward-validation-panel']")).toContainText(
    "命中 11 · 未中 3 · 走水 2",
  );
  await expect(page.locator("[data-ui='forward-validation-panel']")).toContainText(
    "有效输赢 14 场 · 命中率 78.6%",
  );
  const verification = page.locator("[data-ui='forward-validation-panel']");
  await expect(verification).not.toContainText("全部已处理");
  await expect(verification).not.toContainText("历史");
  await expect(verification).not.toContainText("恢复");
  await expect(verification).not.toContainText("审计");
  await expect(verification).not.toContainText("LEGACY");
  const csl = page
    .locator(".d2-league-table > div")
    .filter({ hasText: "中超" });
  await expect(csl).toContainText("1 场");
  await expect(csl).toContainText("0-1-0");
  await expect(csl).toContainText("0.000（n=1）");
  await expect(csl).not.toContainText("0%");
  const norway = page
    .locator(".d2-league-table > div")
    .filter({ hasText: "挪威超" });
  await expect(norway).toContainText("+0.040（n=1）");
  const sweden = page
    .locator(".d2-league-table > div")
    .filter({ hasText: "瑞典超" });
  await expect(sweden).toContainText("-0.020（n=1）");
  const serieA = page
    .locator(".d2-league-table > div")
    .filter({ hasText: "意甲" });
  await expect(serieA).toContainText("--（n=0）");

  await expect(page.locator(".verification-exclusions")).toHaveCount(0);
  await expect(page.locator(".verification-recoveries")).toHaveCount(0);

  await page.setViewportSize({ width: 824, height: 1100 });
  const hasHorizontalOverflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth >
      document.documentElement.clientWidth,
  );
  expect(hasHorizontalOverflow).toBe(false);
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
      .locator("[data-fixture-id]")
      .filter({ hasText: `${scenario} Home` });
    await expect(row).toContainText(scenarioContract[scenario].tierLabel);
    await expect(row).not.toContainText("1.91");
    await expect(row).not.toContainText("正式可锁");
    await expect(page.locator("[data-ui='command-header']")).toContainText(
      "分析建议 0",
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
