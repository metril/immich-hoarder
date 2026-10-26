import { expect, test } from "@playwright/test";

const PAGES = ["Dashboard", "Sources", "Jobs", "Targets", "Credentials", "API Keys", "Users", "Settings"];

test("dashboard loads with no console errors and no CSP violations", async ({ page }) => {
  const problems: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") problems.push(`console: ${m.text()}`);
  });
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  // Settled = dashboard data loaded (no skeletons left), so late console errors would have surfaced.
  await expect(page.getByRole("heading", { name: "Recent uploads" })).toBeVisible();
  await expect(page.getByRole("status", { name: /^Loading/ })).toHaveCount(0);
  expect(problems).toEqual([]);
});

test("deep link /jobs/1 renders job detail with items and log", async ({ page }) => {
  await page.goto("/jobs/1");
  await expect(page.getByText("https://example.test/gallery/0.jpg").first()).toBeVisible();
  await page.getByRole("tab", { name: /log/i }).click();
  await expect(page.getByRole("log")).toContainText("e2e log line 0");
});

test("nav to every admin page via sidebar", async ({ page }) => {
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Main" });
  for (const name of PAGES) {
    await nav.getByRole("link", { name, exact: true }).click();
    // Exactly one h1 per page; the document title tracks the route.
    await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
    await expect(page).toHaveTitle(new RegExp(`^${name} · |^${name}$`));
  }
});

test("cmd+k palette navigates to sources", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Open command palette" }).waitFor();
  await page.keyboard.press("ControlOrMeta+k");
  await page.getByPlaceholder("Type a command or search…").fill("Sources");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/sources/);
});

test("assets served brotli immutable", async ({ page, request }) => {
  await page.goto("/");
  const src = await page.locator("script[type=module][src]").first().getAttribute("src");
  expect(src).toMatch(/^\/assets\//);
  const res = await request.get(src ?? "", { headers: { "accept-encoding": "br" } });
  expect(res.status()).toBe(200);
  expect(res.headers()["content-encoding"]).toBe("br");
  expect(res.headers()["cache-control"]).toContain("immutable");
});

test("theme toggle persists across reload", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Theme" }).click();
  await page.getByRole("menuitemradio", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.reload();
  await expect(page.locator("html")).toHaveClass(/dark/);
  expect(await page.evaluate(() => localStorage.getItem("ih-theme"))).toBe("dark");
});
