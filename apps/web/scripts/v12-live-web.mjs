import assert from "node:assert/strict";
import { chromium } from "@playwright/test";

const base = process.env.W2_V12_WEB_BASE;
const day = process.env.W2_V12_DAY;
const phase = process.env.W2_V12_PHASE;
if (!base || !day || !["PRE_FT", "POST_FT"].includes(phase)) {
  throw new Error("W2_V12_WEB_BASE, W2_V12_DAY and W2_V12_PHASE are required");
}

const browser = await chromium.launch();
try {
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    const page = await browser.newPage({ viewport, colorScheme: "dark" });
    const url = `${base}/?date=${day}`;
    const response = await page.request.get(`${base}/v1/dashboard/intelligence-workspace/list?date=${day}`);
    assert.equal(response.status(), 200, await response.text());
    const api = await response.json();
    const rows = api.today_recommendations.filter((row) => row.fixture_id === "1489404");
    assert.equal(rows.length, 2);
    assert.deepEqual(new Set(rows.map((row) => row.market)), new Set(["ASIAN_HANDICAP", "TOTALS"]));
    assert.equal(api.performance_summary.schema_version, "w2.ah_ou_v3_public_performance.v1");
    await page.goto(url);
    const selector = viewport.width > 500 ? ".w2-table tbody tr[data-decision-id]" : ".w2-cards .w2-card[data-decision-id]";
    try {
      await page.locator(selector).first().waitFor({ timeout: 10_000 });
    } catch (error) {
      console.error(JSON.stringify({ phase, viewport, apiCount: rows.length, body: (await page.locator("body").innerText()).slice(0, 1800) }));
      throw error;
    }
    assert.equal(await page.locator(selector).count(), 2);
    for (const row of rows) {
      const visible = page.locator(`${selector}[data-decision-id="${row.decision_id}"]`);
      assert.equal(await visible.count(), 1, `${row.market} decision missing in ${viewport.width}px UI`);
      const text = await visible.innerText();
      assert.ok(text.includes(row.line), `${row.market} frozen line absent`);
      assert.ok(text.includes(String(row.odds)), `${row.market} frozen price absent`);
      assert.ok(text.includes(phase === "PRE_FT" ? "待赛果" : "已结算"));
      if (phase === "POST_FT") assert.ok(text.includes(String(row.net_units).replace("0.25", "+0.25")) || text.includes("单位"));
    }
    assert.equal(await page.locator('.w2-fixture[data-fixture-id="1489404"]').getAttribute("data-v3-count"), "2");
    await page.locator(selector).first().click();
    const detail = page.locator(".w2-v3-detail-recommendations li[data-decision-id]");
    await detail.first().waitFor();
    assert.equal(await detail.count(), 2);
    for (const row of rows) {
      // The selector itself carries the frozen decision identity, so this
      // checks detail against the same API row rather than a fixture-level pick.
      assert.equal(await detail.filter({ hasText: row.decision_id }).count(), 1);
      assert.equal(await page.locator(`.w2-v3-detail-recommendations li[data-decision-id="${row.decision_id}"]`).count(), 1);
    }
    if (phase === "PRE_FT") {
      assert.equal(api.performance_summary.pending_count, 2);
      assert.equal(api.performance_summary.last_30_days.hit_rate_denominator, 0);
    } else {
      assert.equal(api.performance_summary.settled_count, 2);
      assert.equal(api.performance_summary.total_profit_units, 1.15);
      assert.equal(api.performance_summary.by_market.ASIAN_HANDICAP.profit_units, 0.25);
      assert.equal(api.performance_summary.by_market.TOTALS.profit_units, 0.9);
    }
    console.log(JSON.stringify({ phase, viewport, ids: rows.map((row) => row.decision_id), status: rows.map((row) => row.status), net: api.performance_summary.total_profit_units }));
    await page.close();
  }
} finally {
  await browser.close();
}
