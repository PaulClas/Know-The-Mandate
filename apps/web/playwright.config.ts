import { defineConfig, devices } from "@playwright/test";

// Starts nothing itself by default: assumes the API on :8000 and `npm run dev` / `npm start` on :3000.
// Set PW_START_WEB=1 to let Playwright launch `next dev` for you.
const baseURL = process.env.WEB_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL, trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: process.env.PW_START_WEB
    ? { command: "npm run dev", url: baseURL, reuseExistingServer: true, timeout: 120_000 }
    : undefined,
});
