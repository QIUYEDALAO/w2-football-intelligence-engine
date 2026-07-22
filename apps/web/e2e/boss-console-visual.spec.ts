import { readFileSync, writeFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { kickoffDisplay } from "../src/reference/boss-console/BossDecisionConsoleReference";
import {
  adaptDashboardV2ToBossConsole,
  dedupeLeaguePerformance,
} from "../src/reference/boss-console/boss-console-adapter";
import { bossConsoleFixture } from "../src/reference/boss-console/boss-console.fixture";
import { dashboardV2ReferenceFixture } from "../src/reference/dashboard-v2/dashboard-v2-reference.fixture";

const FIXTURE_URL = "/__visual/boss-console";
const PIXEL_COLOR_THRESHOLD = 0.2;
const VIEWPORTS = [
  { name: "wide-2048", width: 2048, height: 1152 },
  { name: "desktop-1440", width: 1440, height: 900 },
  { name: "mobile-390", width: 390, height: 844 },
] as const;
const SOURCE_HTML = readFileSync(
  new URL("../../../docs/ui/boss-console/w2_boss_decision_console_prototype.html", import.meta.url),
  "utf8",
);

async function freezeMotion(page: Page) {
  await expect(page.locator("[data-ui='boss-decision-console']")).toBeVisible();
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

async function comparePngs(page: Page, reference: Buffer, implementation: Buffer) {
  return page.evaluate(async ({ referenceData, implementationData, colorThreshold }) => {
    const load = (data: string) => new Promise<HTMLImageElement>((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = reject;
      image.src = `data:image/png;base64,${data}`;
    });
    const [expected, actual] = await Promise.all([
      load(referenceData),
      load(implementationData),
    ]);
    if (expected.width !== actual.width || expected.height !== actual.height) {
      return {
        width: actual.width,
        height: actual.height,
        expectedWidth: expected.width,
        expectedHeight: expected.height,
        diffRatio: 1,
      };
    }
    const canvas = document.createElement("canvas");
    canvas.width = expected.width;
    canvas.height = expected.height;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) throw new Error("2D canvas unavailable");
    context.drawImage(expected, 0, 0);
    const expectedPixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.drawImage(actual, 0, 0);
    const actualPixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    const diffCanvas = document.createElement("canvas");
    diffCanvas.width = canvas.width;
    diffCanvas.height = canvas.height;
    const diffContext = diffCanvas.getContext("2d");
    if (!diffContext) throw new Error("Diff canvas unavailable");
    const diffImage = diffContext.createImageData(canvas.width, canvas.height);
    // Keep the 0.15% gate with pixelmatch's standard YIQ threshold and 1px geometry tolerance.
    const maxColorDelta = 35215 * colorThreshold * colorThreshold;
    const pixelMatches = (expectedIndex: number, actualIndex: number) => {
      const red = expectedPixels[expectedIndex] - actualPixels[actualIndex];
      const green = expectedPixels[expectedIndex + 1] - actualPixels[actualIndex + 1];
      const blue = expectedPixels[expectedIndex + 2] - actualPixels[actualIndex + 2];
      const luminance = 0.29889531 * red + 0.58662247 * green + 0.11448223 * blue;
      const chromaI = 0.59597799 * red - 0.2741761 * green - 0.32180189 * blue;
      const chromaQ = 0.21147017 * red - 0.52261711 * green + 0.31114694 * blue;
      const colorDelta = 0.5053 * luminance * luminance
        + 0.299 * chromaI * chromaI
        + 0.1957 * chromaQ * chromaQ;
      return colorDelta <= maxColorDelta;
    };
    let changed = 0;
    for (let y = 0; y < canvas.height; y += 1) {
      for (let x = 0; x < canvas.width; x += 1) {
        const expectedIndex = (y * canvas.width + x) * 4;
        let matched = pixelMatches(expectedIndex, expectedIndex);
        for (let dy = -1; !matched && dy <= 1; dy += 1) {
          for (let dx = -1; !matched && dx <= 1; dx += 1) {
            const actualX = x + dx;
            const actualY = y + dy;
            if (actualX < 0 || actualX >= canvas.width || actualY < 0 || actualY >= canvas.height) continue;
            matched = pixelMatches(expectedIndex, (actualY * canvas.width + actualX) * 4);
          }
        }
        const diffIndex = expectedIndex;
        if (!matched) {
          changed += 1;
          diffImage.data[diffIndex] = 255;
          diffImage.data[diffIndex + 1] = 74;
          diffImage.data[diffIndex + 2] = 74;
          diffImage.data[diffIndex + 3] = 255;
        } else {
          diffImage.data[diffIndex] = 7;
          diffImage.data[diffIndex + 1] = 16;
          diffImage.data[diffIndex + 2] = 13;
          diffImage.data[diffIndex + 3] = 255;
        }
      }
    }
    diffContext.putImageData(diffImage, 0, 0);
    return {
      width: actual.width,
      height: actual.height,
      expectedWidth: expected.width,
      expectedHeight: expected.height,
      diffRatio: changed / (canvas.width * canvas.height),
      diffPng: diffCanvas.toDataURL("image/png").split(",")[1],
    };
  }, {
    referenceData: reference.toString("base64"),
    implementationData: implementation.toString("base64"),
    colorThreshold: PIXEL_COLOR_THRESHOLD,
  });
}

test.describe("Boss Decision Console source contract", () => {
  test.use({
    viewport: { width: 1440, height: 900 },
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    deviceScaleFactor: 1,
  });

  test("React implementation matches the approved HTML authority at all viewports", async ({ page }) => {
    for (const viewport of VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.setContent(SOURCE_HTML, { waitUntil: "load" });
      await expect(page.locator("#decisionList .decision-row")).toHaveCount(5);
      const reference = await page.screenshot({
        path: `/tmp/w2-boss-v2-reference-${viewport.name}.png`,
        fullPage: true,
        animations: "disabled",
      });

      await page.goto(FIXTURE_URL);
      await freezeMotion(page);
      const implementation = await page.screenshot({
        path: `/tmp/w2-boss-v2-actual-${viewport.name}.png`,
        fullPage: true,
        animations: "disabled",
      });
      const comparison = await comparePngs(page, reference, implementation);
      writeFileSync(
        `/tmp/w2-boss-v2-diff-${viewport.name}.png`,
        Buffer.from(comparison.diffPng, "base64"),
      );

      expect(comparison.width).toBe(comparison.expectedWidth);
      expect(comparison.height).toBe(comparison.expectedHeight);
      expect(comparison.diffRatio).toBeLessThanOrEqual(0.0015);
      console.log(`[boss-console-pixel] ${viewport.name} diff_ratio=${comparison.diffRatio.toFixed(8)}`);
    }
  });

  test("filters, selection and system drawer preserve the source behavior", async ({ page }) => {
    await page.goto(FIXTURE_URL);
    await freezeMotion(page);

    await expect(page.locator("[data-fixture-id]")).toHaveCount(5);
    await page.getByRole("button", { name: "全部赛程 14/14 场" }).click();
    await expect(page.locator("[data-fixture-id]")).toHaveCount(14);

    const row = page.locator("[data-fixture-id='1494223']");
    await row.click();
    await expect(row).toHaveClass(/is-selected/);
    await expect(page.locator("[data-ui='selected-match-panel']")).toContainText(
      "天狼星 vs 哥德堡",
    );

    await page.getByRole("button", { name: "仅看异常" }).click();
    await expect(page.locator("[data-fixture-id]")).toHaveCount(7);

    await page.getByRole("button", { name: "打开系统状态" }).click();
    const drawer = page.locator(".drawer-backdrop");
    await expect(drawer).toHaveAttribute("aria-hidden", "false");
    await page.keyboard.press("Escape");
    await expect(drawer).toHaveAttribute("aria-hidden", "true");
  });

  test("all fixtures stay reachable through the source queue viewport", async ({ page }) => {
    await page.goto(FIXTURE_URL);
    await freezeMotion(page);
    await page.getByRole("button", { name: "全部赛程 14/14 场" }).click();

    const queue = page.locator("[data-ui='schedule-scroller']");
    const before = await queue.evaluate((node) => ({
      clientHeight: node.clientHeight,
      scrollHeight: node.scrollHeight,
    }));
    expect(before.scrollHeight).toBeGreaterThan(before.clientHeight);

    const last = page.locator("[data-fixture-id='future-6']");
    await last.scrollIntoViewIfNeeded();
    await expect(last).toBeInViewport();
    await last.click();
    await expect(page.locator("[data-ui='selected-match-panel']")).toContainText(
      "埃尔夫斯堡 vs 米亚尔比",
    );
  });

  test("production truth boundaries remain explicit", async ({ page }) => {
    await page.goto(FIXTURE_URL);
    await freezeMotion(page);
    await expect(page.locator(".topbar")).toContainText("正式建议0");
    await expect(page.locator(".risk-strip")).toContainText("自动采集当前暂停");
    await expect(page.locator("[data-ui='forward-validation-panel']")).toContainText(
      "有效输赢命中率 78.6%（11/14）",
    );
    await expect(page.locator(".footer-note")).toContainText(
      "分析建议 ≠ 正式推荐",
    );
    await expect(page.locator("body")).not.toContainText("历史恢复 cohort");
    await expect(page.locator("body")).not.toContainText("当前 V3 cohort");
    await expect(page.locator("body")).not.toContainText("不与历史混算");
  });

  test("date-first presentation covers boundary and lifecycle states", () => {
    const now = new Date("2026-07-21T12:33:00Z");
    expect(kickoffDisplay("2026-07-25T13:00:00Z", "NS", now)).toEqual({
      primary: "07-25 周六",
      secondary: "21:00",
      tertiary: "4天后",
    });
    expect(kickoffDisplay("2026-07-22T12:00:00Z", "NS", now).primary).toBe("明天");
    expect(kickoffDisplay("2026-07-21T13:16:00Z", "NS", now).tertiary).toBe("还有 43分钟");
    expect(kickoffDisplay("2026-07-21T14:48:00Z", "NS", now).tertiary).toBe("还有 2小时15分");
    expect(kickoffDisplay("2027-01-01T12:00:00Z", "NS", new Date("2026-12-31T15:00:00Z"))).toEqual({
      primary: "明天",
      secondary: "20:00",
      tertiary: "01-01 周五",
    });
    expect(kickoffDisplay("2026-07-25T13:00:00Z", "LIVE 63", now).primary).toBe("进行中 63′");
    expect(kickoffDisplay("2026-07-25T13:00:00Z", "FINISHED", now).primary).toBe("完场");
    expect(kickoffDisplay("invalid", "NS", now).primary).toBe("时间待定");
  });

  test("the minute clock advances countdowns without a data refresh", async ({ page }) => {
    await page.clock.install({ time: new Date("2026-07-21T12:33:00Z") });
    await page.goto(`${FIXTURE_URL}?liveClock=1&nearKickoff=1`);
    await freezeMotion(page);
    const firstKickoff = page.locator("[data-fixture-id='1494218'] .kickoff");
    await expect(firstKickoff).toContainText(/还有 4[23]分钟/);
    const pageRefresh = await page.locator(".snapshot-time").filter({ hasText: "页面刷新" }).textContent();
    await page.clock.fastForward(60_000);
    await expect(firstKickoff).toContainText(/还有 4[12]分钟/);
    await expect(page.locator(".snapshot-time").filter({ hasText: "页面刷新" })).toHaveText(pageRefresh ?? "");
  });

  test("time sequence anomalies fail visibly and expose exact fields in L2", async ({ page }) => {
    await page.goto(`${FIXTURE_URL}?timeAnomaly=1`);
    await freezeMotion(page);
    await expect(page.locator(".topbar")).toContainText("时间状态异常");
    await page.getByRole("button", { name: "打开系统状态" }).click();
    await expect(page.locator(".system-item.anomaly")).toContainText("odds=2026-07-21T13:00:00Z");
    await expect(page.locator(".system-item.anomaly")).toContainText("page=2026-07-21T12:33:00Z");
  });

  test("Boss adapter preserves the backend scoreline projection order", () => {
    const model = adaptDashboardV2ToBossConsole(dashboardV2ReferenceFixture);
    expect(model.decisions[0].scorelineProjection).toEqual(
      dashboardV2ReferenceFixture.fixtures[0].scorelineProjection,
    );
    expect(model.decisions[0].scorelineProjection?.top3.map((row) => row.scoreline)).toEqual([
      "0-1",
      "0-2",
      "1-2",
    ]);
  });

  test("scoreline display keeps sample counts, constraints and blockers truthful", async ({ page }) => {
    await page.goto(FIXTURE_URL);
    await freezeMotion(page);
    const first = page.locator("[data-fixture-id='1494218']");
    await expect(first).toContainText("模型比分 0-1 · 0-2 · 1-2");
    const projection = page.locator("[data-ui='scoreline-projection']");
    await expect(projection).toContainText("10,000 次模拟");
    await expect(projection).toContainText("0-111.3%1,130次");
    await expect(projection).toContainText("一致样本 6,417 / 10,000");
    await expect(projection).toContainText("全部符合：客队 -0.75");

    await page.goto(`${FIXTURE_URL}?scorelineNotReady=1`);
    await freezeMotion(page);
    await expect(page.locator("[data-ui='scoreline-projection']")).toContainText(
      "SCORELINE_CONSTRAINT_EMPTY",
    );
  });

  test("the fixed workspace exposes every 5, 15 and 30 fixture row", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    let workspaceHeight: number | null = null;
    for (const count of [5, 15, 30]) {
      await page.goto(`${FIXTURE_URL}?count=${count}`);
      await freezeMotion(page);
      await page.getByRole("button", { name: `全部赛程 ${count}/${count} 场` }).click();
      await expect(page.locator("[data-fixture-id]")).toHaveCount(count);
      const workspace = page.locator(".workspace");
      const height = await workspace.evaluate((node) => node.getBoundingClientRect().height);
      workspaceHeight ??= height;
      expect(Math.abs(height - workspaceHeight)).toBeLessThanOrEqual(1);
      const queue = page.locator("[data-ui='schedule-scroller']");
      const header = page.locator(".decision-table-head");
      const headerY = await header.evaluate((node) => node.getBoundingClientRect().y);
      if (count > 5) {
        const geometry = await queue.evaluate((node) => ({ clientHeight: node.clientHeight, scrollHeight: node.scrollHeight }));
        expect(geometry.scrollHeight).toBeGreaterThan(geometry.clientHeight);
        await queue.evaluate((node) => { node.scrollTop = node.scrollHeight; });
        expect(Math.abs((await header.evaluate((node) => node.getBoundingClientRect().y)) - headerY)).toBeLessThanOrEqual(1);
      }
      const last = page.locator("[data-fixture-id]").last();
      await last.scrollIntoViewIfNeeded();
      await expect(last).toBeInViewport();
      await expect(header).toBeVisible();
      await last.click();
      await expect(last).toHaveClass(/is-selected/);
      await expect(page.locator("[data-ui='selected-match-panel']")).toBeVisible();
    }
  });

  test("mobile uses natural document scrolling with all 30 fixtures reachable", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${FIXTURE_URL}?count=30`);
    await freezeMotion(page);
    await page.getByRole("button", { name: "全部赛程 30/30 场" }).click();
    const queue = page.locator("[data-ui='schedule-scroller']");
    await expect(queue).toHaveCSS("overflow-y", "visible");
    await expect(page.locator("[data-fixture-id]")).toHaveCount(30);
    const last = page.locator("[data-fixture-id]").last();
    await last.scrollIntoViewIfNeeded();
    await expect(last).toBeInViewport();
  });

  test("league rows dedupe by canonical key without inflating zero-sample aliases", () => {
    const rows = dedupeLeaguePerformance([
      { competitionKey: "allsvenskan", league: "瑞典超", eligibleCount: 4, hitCount: 3, missCount: 1, pushCount: 0, clvMedian: -0.02, clvSampleCount: 1, statusLabel: "样本不足" },
      { competitionKey: "allsvenskan", league: "Allsvenskan", eligibleCount: 0, hitCount: 0, missCount: 0, pushCount: 0, clvMedian: null, clvSampleCount: 0, statusLabel: "样本不足" },
      { competitionKey: "other-league", league: "瑞典超", eligibleCount: 2, hitCount: 1, missCount: 1, pushCount: 0, clvMedian: null, clvSampleCount: 0, statusLabel: "样本不足" },
    ]);
    expect(rows).toHaveLength(2);
    expect(rows.filter((row) => row.competitionKey === "allsvenskan")).toHaveLength(1);
    expect(rows.find((row) => row.competitionKey === "allsvenskan")?.eligibleCount).toBe(4);
  });

  test("fixture scorelines satisfy the frozen public market examples", () => {
    const [away075, under35, away125, over25] = bossConsoleFixture.decisions;
    expect(away075.scorelineProjection?.top3.every((row) => ["WIN", "HALF_WIN"].includes(row.primarySettlement))).toBe(true);
    expect(away075.scorelineProjection?.top3.every((row) => {
      const [home, away] = row.scoreline.split("-").map(Number);
      return away - home >= 1;
    })).toBe(true);
    expect(away125.scorelineProjection?.top3.every((row) => ["WIN", "HALF_WIN"].includes(row.primarySettlement))).toBe(true);
    expect(away125.scorelineProjection?.top3.every((row) => {
      const [home, away] = row.scoreline.split("-").map(Number);
      return away - home >= 2;
    })).toBe(true);
    expect(under35.scorelineProjection?.top3.every((row) => row.scoreline.split("-").map(Number).reduce((sum, goal) => sum + goal, 0) <= 3)).toBe(true);
    expect(over25.scorelineProjection?.top3.every((row) => row.scoreline.split("-").map(Number).reduce((sum, goal) => sum + goal, 0) >= 3)).toBe(true);
  });
});
