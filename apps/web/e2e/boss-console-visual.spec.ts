import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

const FIXTURE_URL = "/__visual/boss-console";
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
  return page.evaluate(async ({ referenceData, implementationData }) => {
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
    // Keep the 0.15% gate while tolerating one-pixel glyph rasterization drift on Linux.
    const pixelMatches = (expectedIndex: number, actualIndex: number) => Math.max(
      Math.abs(expectedPixels[expectedIndex] - actualPixels[actualIndex]),
      Math.abs(expectedPixels[expectedIndex + 1] - actualPixels[actualIndex + 1]),
      Math.abs(expectedPixels[expectedIndex + 2] - actualPixels[actualIndex + 2]),
      Math.abs(expectedPixels[expectedIndex + 3] - actualPixels[actualIndex + 3]),
    ) <= 12;
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
        if (!matched) changed += 1;
      }
    }
    return {
      width: actual.width,
      height: actual.height,
      expectedWidth: expected.width,
      expectedHeight: expected.height,
      diffRatio: changed / (canvas.width * canvas.height),
    };
  }, {
    referenceData: reference.toString("base64"),
    implementationData: implementation.toString("base64"),
  });
}

test.describe("Boss Decision Console source contract", () => {
  test.use({
    viewport: { width: 1440, height: 900 },
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    deviceScaleFactor: 1,
  });

  test("React implementation matches the approved HTML authority", async ({ page }) => {
    await page.setContent(SOURCE_HTML, { waitUntil: "load" });
    await expect(page.locator("#decisionList .decision-row")).toHaveCount(5);
    const reference = await page.screenshot({
      path: "/tmp/w2-boss-reference.png",
      fullPage: true,
      animations: "disabled",
    });

    await page.goto(FIXTURE_URL);
    await freezeMotion(page);
    const implementation = await page.screenshot({
      path: "/tmp/w2-boss-implementation.png",
      fullPage: true,
      animations: "disabled",
    });
    const comparison = await comparePngs(page, reference, implementation);

    expect(comparison.width).toBe(comparison.expectedWidth);
    expect(comparison.height).toBe(comparison.expectedHeight);
    expect(comparison.diffRatio).toBeLessThanOrEqual(0.0015);
  });

  test("filters, selection and system drawer preserve the source behavior", async ({ page }) => {
    await page.goto(FIXTURE_URL);
    await freezeMotion(page);

    await expect(page.locator("[data-fixture-id]")).toHaveCount(5);
    await page.getByRole("button", { name: "全部赛程 14" }).click();
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
    await page.getByRole("button", { name: "全部赛程 14" }).click();

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
  });
});
