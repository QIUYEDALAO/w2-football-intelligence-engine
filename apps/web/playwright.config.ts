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
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: `npm run dev -- --port ${port} --strictPort`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
