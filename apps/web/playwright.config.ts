import { defineConfig, devices } from "@playwright/test";

const port = process.env.W2_PLAYWRIGHT_PORT || "4173";
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./e2e",
  snapshotPathTemplate: "../../docs/ui/dashboard-v4.1/targets/{arg}{ext}",
  fullyParallel: false,
  retries: 0,
  reporter: "line",
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      // 既有 e2e 断言按深色主题写就；显式固定 prefers-color-scheme，避免
      // 浅色主题变量让颜色断言漂移。
      use: { ...devices["Desktop Chrome"], colorScheme: "dark" },
    },
  ],
  webServer: {
    command: `npm run dev -- --port ${port} --strictPort`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
