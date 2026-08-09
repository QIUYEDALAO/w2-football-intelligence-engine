import { expect, test } from "@playwright/test";

test("legacy performance route is no longer a second public dashboard", async ({ page }) => {
  const requested: string[] = [];
  await page.route("**/v1/**", async (route) => {
    requested.push(new URL(route.request().url()).pathname);
    if (new URL(route.request().url()).pathname !== "/v1/dashboard/intelligence-workspace") {
      return route.fulfill({ status: 418, json: { error: "LEGACY_PUBLIC_READ_FORBIDDEN" } });
    }
    return route.fulfill({ status: 503, json: { code: "UNIFIED_WORKSPACE_REQUIRED" } });
  });
  await page.goto("/performance");
  await expect(page.locator(".workspace-load-state--error")).toContainText("统一情报工作台暂不可用");
  expect(new Set(requested)).toEqual(new Set(["/v1/dashboard/intelligence-workspace"]));
  await expect(page.locator("body")).not.toContainText("CLV 点分布");
});
