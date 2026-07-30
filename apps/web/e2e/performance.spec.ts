import { expect, test } from "@playwright/test";

function payload(pointCount = 0) {
  const bins = Array.from({ length: 10 }, (_, index) => ({
    lower: index / 10,
    upper: (index + 1) / 10,
    count: pointCount ? 1 : 0,
    mean_confidence: pointCount ? (index + 0.5) / 10 : null,
    accuracy: pointCount ? index / 10 : null,
  }));
  const tierRow = (tier: "STRICT" | "ADVISORY") => ({
    tier,
    finished_result_count: tier === "STRICT" ? 20 : 15,
    scored_count: pointCount,
    canonical_settled_count: pointCount,
    canonical_hit_rate: null,
    canonical_hit_rate_status: "INSUFFICIENT_SAMPLE",
    clv_mean: pointCount ? 0.04 : null,
    clv_positive_share: pointCount ? 0.6 : null,
  });
  return {
    request_id: "performance-e2e",
    projection_version: "eval-02a.v1",
    scoring_window_anchor: "2026-07-30T00:00:00Z",
    selected_window: "30d",
    selected_league: null,
    selected_tier: "ALL",
    clv: {
      clv_population: "SCORABLE_FINISHED_WITH_CANONICAL_CLV",
      sample_count: pointCount,
      mean: pointCount ? 0.04 : null,
      median: pointCount ? 0.03 : null,
      ci95: pointCount ? [0.01, 0.07] : null,
      positive_count: pointCount ? 9 : 0,
      positive_share: pointCount ? 0.6 : null,
      method: "canonical-entry-minus-closing",
      points: Array.from({ length: pointCount }, (_, index) => ({
        fixture_id: `fixture-${String(index + 1).padStart(2, "0")}`,
        kickoff_utc: "2026-07-29T12:00:00Z",
        league: index % 2 ? "brasileirao_serie_a" : "premier_league",
        evaluation_tier: index % 2 ? "ADVISORY" : "STRICT",
        clv_decimal: (index - 5) / 100,
      })),
    },
    calibration: {
      scored_count: pointCount,
      model_log_loss: pointCount ? 0.59 : null,
      market_log_loss: pointCount ? 0.64 : null,
      model_minus_market_log_loss: pointCount ? -0.05 : null,
      model_ece: pointCount ? 0.06 : null,
      market_ece: pointCount ? 0.08 : null,
      model_reliability_bins: bins,
      market_reliability_bins: bins,
      paired_log_loss_bootstrap: {
        status: pointCount ? "AVAILABLE" : "INSUFFICIENT",
        sample_count: pointCount,
      },
    },
    tier_comparison: {
      STRICT: tierRow("STRICT"),
      ADVISORY: tierRow("ADVISORY"),
    },
    sample_progress: {
      current: pointCount,
      target: 200,
      ratio: pointCount / 200,
      status: "ACCUMULATING",
    },
    coverage: {
      finished_result_count: 35,
      fixture_checkpoint_count: 35,
      scored_count: pointCount,
      not_scorable_count: 35 - pointCount,
      blocked_count: 0,
      not_scorable_by_reason: pointCount
        ? {}
        : { CAPTURE_IDENTITY_MISSING: 31 },
    },
    checkpoint_metadata: {
      checkpoint_key: "performance:cohort:all",
      source_hash: "stable-performance-hash",
      created_at: "2026-07-30T00:00:00Z",
    },
  };
}

test("renders the real zero-sample production state without fake metrics", async ({
  page,
}) => {
  await page.route("**/v1/performance?**", (route) =>
    route.fulfill({ json: payload() }),
  );

  await page.goto("/performance");

  await expect(
    page.getByText("总体：已完成全量评分且具有 canonical CLV 的比赛"),
  ).toBeVisible();
  await expect(page.getByText("暂无 canonical CLV 样本")).toBeVisible();
  await expect(page.getByText("暂无可评分样本")).toBeVisible();
  await expect(page.getByText("0 / 200")).toBeVisible();
  await expect(
    page.getByText(/覆盖：35 场已投影，\s*35 场不可评分，\s*0 场阻断/),
  ).toBeVisible();
  await expect(page.getByRole("cell", { name: "样本不足" }).first()).toBeVisible();
});

for (const pointCount of [15, 30]) {
  test(`${pointCount}-match visual stays bounded and internally scrollable`, async ({
    page,
  }, testInfo) => {
    await page.route("**/v1/performance?**", (route) =>
      route.fulfill({ json: payload(pointCount) }),
    );

    await page.goto("/performance");
    const points = page.getByLabel("CLV 点分布");

    await expect(points.locator("li")).toHaveCount(pointCount);
    expect(
      await points.evaluate(
        (element) => element.scrollHeight > element.clientHeight,
      ),
    ).toBe(true);
    await page.screenshot({
      path: testInfo.outputPath(`performance-${pointCount}.png`),
      fullPage: true,
    });
  });
}

test("shows a fail-closed API state without demo fallback", async ({ page }) => {
  await page.route("**/v1/performance?**", (route) =>
    route.fulfill({ status: 503, json: { code: "SYSTEM_DEGRADED" } }),
  );

  await page.goto("/performance");

  await expect(page.getByText("表现投影暂不可用")).toBeVisible();
  await expect(page.getByText("SYSTEM_DEGRADED")).toBeVisible();
  await expect(page.getByText(/不会用旧 Dashboard/)).toBeVisible();
});
