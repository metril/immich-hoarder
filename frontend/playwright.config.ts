import { defineConfig, devices } from "@playwright/test";

const PORT = process.env.E2E_PORT ?? "8090";

export default defineConfig({
  testDir: "e2e",
  testIgnore: process.env.SCREENSHOTS ? [] : ["**/screenshots.spec.ts"],
  fullyParallel: true,
  expect: { timeout: 10_000 },
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL: `http://127.0.0.1:${PORT}`, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "cd ../backend && uv run python -m tests.e2e_server",
    url: `http://127.0.0.1:${PORT}/healthz`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
