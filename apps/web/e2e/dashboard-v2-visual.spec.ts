import { expect, test } from "@playwright/test";

const FIXTURE_URL = "/__visual/dashboard-v2";

async function freezeMotion(page: import("@playwright/test").Page) {
  await expect(page.locator("[data-ui='dashboard-workspace']")).toBeVisible();
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation: none !important;
        transition: none !important;
        caret-color: transparent !important;
      }
      html { scroll-behavior: auto !important; }
    `,
  });
}

test.describe("Dashboard V2 pixel contract", () => {
  test.use({ locale: "zh-CN", timezoneId: "Asia/Shanghai", deviceScaleFactor: 1 });

  for (const viewport of [
    { name: "wide-2048", width: 2048, height: 1152 },
    { name: "desktop-1440", width: 1440, height: 900 },
  ]) {
    test(`${viewport.name} visual baseline`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto(FIXTURE_URL);
      await freezeMotion(page);
      await expect(page).toHaveScreenshot(
        `dashboard-v2-${viewport.name}.png`,
        {
          animations: "disabled",
          caret: "hide",
          fullPage: true,
          maxDiffPixelRatio: 0.0015,
        },
      );
    });
  }

  test("mobile-390 visual baseline", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(FIXTURE_URL);
    await freezeMotion(page);
    await expect(page).toHaveScreenshot(
      "dashboard-v2-mobile-390.png",
      { animations: "disabled", caret: "hide", fullPage: true, maxDiffPixelRatio: 0.0015 },
    );
  });
});

test.describe("Dashboard V2 geometry and behavior contract", () => {
  test.use({
    viewport: { width: 2048, height: 1152 },
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    deviceScaleFactor: 1,
  });

  test("all 15 fixtures are reachable inside the schedule scroller", async ({ page }) => {
    await page.goto(FIXTURE_URL);
    await freezeMotion(page);

    const dashboard = page.locator("[data-ui='dashboard-workspace']");
    const schedule = page.locator("[data-ui='schedule-scroller']");
    const rail = page.locator("[data-ui='evidence-rail']");

    await expect(page.getByText("15 / 15 场")).toBeVisible();
    await expect(page.locator("[data-fixture-id]")).toHaveCount(15);

    const before = await schedule.evaluate((node) => ({
      clientHeight: node.clientHeight,
      scrollHeight: node.scrollHeight,
      scrollTop: node.scrollTop,
    }));
    expect(before.scrollHeight).toBeGreaterThan(before.clientHeight);

    const dashboardBox = await dashboard.boundingBox();
    const scheduleBox = await schedule.boundingBox();
    const railBox = await rail.boundingBox();
    expect(dashboardBox).not.toBeNull();
    expect(scheduleBox).not.toBeNull();
    expect(railBox).not.toBeNull();
    expect(Math.abs((scheduleBox?.height ?? 0) - (dashboardBox?.height ?? 0))).toBeLessThanOrEqual(1);
    expect(Math.abs((railBox?.y ?? 0) - (dashboardBox?.y ?? 0))).toBeLessThanOrEqual(1);

    await schedule.evaluate((node) => {
      node.scrollTop = node.scrollHeight;
    });
    const lastFixture = page.locator("[data-fixture-id='el-003']");
    await expect(lastFixture).toBeVisible();
    await expect(lastFixture).toBeInViewport();
    await expect(page.locator("[data-ui='selected-match-panel']")).toBeVisible();
    await expect(page.locator("[data-ui='scoreline-top3-panel']")).toBeVisible();
    const after = await schedule.evaluate((node) => ({ scrollTop: node.scrollTop }));
    expect(after.scrollTop).toBeGreaterThan(0);
  });

  test("scoreline panel is market-consistent and fully visible", async ({ page }) => {
    await page.goto(FIXTURE_URL);
    await freezeMotion(page);

    const panel = page.locator("[data-ui='scoreline-top3-panel']");
    await expect(panel).toContainText("模型比分 Top 3");
    await expect(panel).toContainText("10,000 次模拟");
    await expect(panel).toContainText("全部符合：客队 -0.75 · 次推小 3.5");
    await expect(panel).toContainText("0-1");
    await expect(panel).toContainText("0-2");
    await expect(panel).toContainText("1-2");
    const panelBox = await panel.boundingBox();
    const railBox = await page.locator("[data-ui='evidence-rail']").boundingBox();
    expect(panelBox).not.toBeNull();
    expect(railBox).not.toBeNull();
    expect(panelBox?.x).toBeGreaterThanOrEqual(railBox?.x ?? 0);
    expect((panelBox?.x ?? 0) + (panelBox?.width ?? 0)).toBeLessThanOrEqual(
      (railBox?.x ?? 0) + (railBox?.width ?? 0) + 1,
    );
  });

  test("public ledger uses one unified accounting identity", async ({ page }) => {
    await page.goto(FIXTURE_URL);
    const ledger = page.locator("[data-ui='forward-ledger-strip']");
    const validation = page.locator("[data-ui='forward-validation-panel']");

    await expect(ledger).toContainText("前向验证账本");
    await expect(ledger).toContainText("记录 26");
    await expect(ledger).toContainText("已结算 23");
    await expect(ledger).toContainText("纳入 16");
    await expect(ledger).toContainText("证据待补 7");
    await expect(ledger).toContainText("待结算 3");
    await expect(ledger).toContainText("78.6%（11/14）");
    await expect(validation).toContainText("26 = 23 已结算 + 3 待结算");
    await expect(validation).toContainText("23 = 16 纳入 + 7 证据待补");
    await expect(page.getByText(/历史恢复 cohort/)).toHaveCount(0);
  });
});
