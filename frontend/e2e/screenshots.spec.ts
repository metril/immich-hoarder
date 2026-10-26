import { statSync } from "node:fs";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

const OUT = path.resolve(process.cwd(), "../docs/assets/screenshots");
const MAX_BYTES = 400 * 1024;
const FIRST_ROW = '[role="row"][aria-rowindex="2"]';
const THEMES = ["light", "dark"] as const;

// Settled = heading visible and no loading skeletons/spinners left. Not networkidle: the SSE stream never idles.
async function settle(page: Page, heading: string | RegExp) {
  await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
  await expect(page.getByRole("status", { name: /^Loading/ })).toHaveCount(0);
  await expect(page.getByText(/^Loading/)).toHaveCount(0);
}

async function shot(page: Page, name: string) {
  const file = path.join(OUT, `${name}.png`);
  await page.screenshot({ path: file });
  expect(statSync(file).size).toBeLessThan(MAX_BYTES);
}

test.beforeAll(() => mkdirSync(OUT, { recursive: true }));

for (const theme of THEMES) {
  test.describe(theme, () => {
    test.use({ viewport: { width: 1440, height: 900 } });
    test.beforeEach(async ({ page }) => {
      await page.addInitScript((t) => localStorage.setItem("ih-theme", t), theme);
    });

    test("dashboard", async ({ page }) => {
      await page.goto("/");
      await settle(page, /Dashboard|Welcome/);
      await expect(page.getByRole("heading", { name: "Recent uploads" })).toBeVisible();
      await shot(page, `dashboard-${theme}`);
    });

    test("sources and editor", async ({ page }) => {
      await page.goto("/sources");
      await settle(page, "Sources");
      await expect(page.locator(FIRST_ROW)).toBeVisible();
      await shot(page, `sources-${theme}`);
      await page.locator(FIRST_ROW).getByRole("button", { name: /^Edit/ }).click();
      const dialog = page.getByRole("dialog");
      await expect(dialog).toBeVisible();
      await expect(dialog.getByText(/^Loading/)).toHaveCount(0);
      await expect(dialog.getByLabel("Name")).toBeVisible();
      await shot(page, `source-editor-${theme}`);
    });

    test("job detail", async ({ page }) => {
      await page.goto("/jobs");
      await settle(page, "Jobs");
      await page.locator(FIRST_ROW).click();
      await settle(page, /^Job #/);
      await expect(page.getByText("https://example.test/gallery/0.jpg").first()).toBeVisible();
      await shot(page, `job-detail-${theme}`);
    });

    test("settings", async ({ page }) => {
      await page.goto("/settings");
      await settle(page, "Settings");
      await shot(page, `settings-${theme}`);
    });
  });
}

test.describe("mobile", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test("dashboard mobile dark", async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("ih-theme", "dark"));
    await page.goto("/");
    await settle(page, /Dashboard|Welcome/);
    await expect(page.getByRole("heading", { name: "Recent uploads" })).toBeVisible();
    await shot(page, "dashboard-mobile-dark");
  });
});
