import { statSync } from "node:fs";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

const OUT = path.resolve(process.cwd(), "../docs/assets/screenshots");
const MAX_BYTES = 400 * 1024;
const FIRST_ROW = '[role="row"][aria-rowindex="2"]';
const THEMES = ["light", "dark"] as const;
const BASE = `http://127.0.0.1:${process.env.E2E_PORT ?? "8090"}`;

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
      await page.locator(FIRST_ROW).getByRole("button", { name: /^More actions/ }).click();
      await page.getByRole("menuitem", { name: /^Edit/ }).click();
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

const EXTRA = [
  { name: "jobs", path: "/jobs", heading: "Jobs" },
  { name: "targets", path: "/targets", heading: "Targets" },
  { name: "users", path: "/users", heading: "Users" },
];

for (const theme of THEMES) {
  test.describe(`extra ${theme}`, () => {
    test.use({ viewport: { width: 1440, height: 900 } });
    test.beforeEach(async ({ page }) => {
      await page.addInitScript((t) => localStorage.setItem("ih-theme", t), theme);
    });
    for (const p of EXTRA) {
      test(p.name, async ({ page }) => {
        await page.goto(p.path);
        await settle(page, p.heading);
        await shot(page, `${p.name}-${theme}`);
      });
    }
    test("login", async ({ page }) => {
      await page.context().addCookies([
        { name: "session", value: "invalid", url: BASE },
        { name: "ih_csrf", value: "e2e", url: BASE },
      ]);
      await page.goto("/login");
      await expect(page.getByRole("link", { name: /Sign in/ })).toBeVisible();
      await shot(page, `login-${theme}`);
    });
    test("source row menu", async ({ page }) => {
      await page.goto("/sources");
      await settle(page, "Sources");
      await page.locator(FIRST_ROW).getByRole("button", { name: /^More actions/ }).click();
      await expect(page.getByRole("menuitem").first()).toBeVisible();
      await page.waitForTimeout(300); // let the open animation finish
      await shot(page, `sources-menu-${theme}`);
    });
  });
}

for (const theme of THEMES) {
  test.describe(`mobile ${theme}`, () => {
    test.use({ viewport: { width: 390, height: 844 } });
    test.beforeEach(async ({ page }) => {
      await page.addInitScript((t) => localStorage.setItem("ih-theme", t), theme);
    });
    for (const p of [{ name: "dashboard", path: "/", heading: /Dashboard|Welcome/ }, { name: "sources", path: "/sources", heading: "Sources" }, ...EXTRA, { name: "settings", path: "/settings", heading: "Settings" }]) {
      test(p.name, async ({ page }) => {
        await page.goto(p.path);
        await settle(page, p.heading);
        await shot(page, `${p.name}-mobile-${theme}`);
      });
    }
  });
}
