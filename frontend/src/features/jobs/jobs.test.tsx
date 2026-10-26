import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { MeOut } from "../../api/me";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { FakeEventSource } from "../../test/setup";

const user = userEvent.setup({ delay: null });

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
const me: MeOut = { id: 1, name: "Own", email: "o@x.io", groups: [], role: "user" };
const job = (id: number, o: Record<string, unknown> = {}) => ({
  id, status: "running", counters: { uploaded: 2, failed: 0 }, phase: null, source_id: 3, source_name: "Cats",
  created_at: "2026-10-26T10:00:00Z", started_at: "2026-10-26T10:00:00Z", finished_at: null, error: null, log_level: null, triggered_by: 1, ...o,
});
const source = { id: 3, name: "Cats", target_id: 7 };
const page = (items: unknown[]) => HttpResponse.json({ items, next_cursor: null });

beforeAll(() => Promise.all([import("./JobsPage"), import("./JobDetail")]), 30_000);

function setup(route: string, j: Record<string, unknown> = {}, items: unknown[] = []) {
  server.use(
    http.get("*/api/v1/jobs", () => page([job(1, j)])),
    http.get("*/api/v1/jobs/1", () => HttpResponse.json(job(1, j))),
    http.get("*/api/v1/jobs/1/items", () => page(items)),
    http.get("*/api/v1/sources", () => page([source])),
    http.get("*/api/v1/sources/3", () => HttpResponse.json(source)),
  );
  return renderWithProviders(null, { me, route });
}
const streamFor = (frag: string) => FakeEventSource.instances.filter((e) => e.url.includes(frag)).at(-1)!;

describe("jobs list", () => {
  it("status filter updates url and query", async () => {
    let seen: string | null = null;
    setup("/jobs");
    server.use(http.get("*/api/v1/jobs", ({ request }) => { seen = new URL(request.url).searchParams.get("status"); return page([job(1)]); }));
    await screen.findByText("#1");
    await user.click(screen.getByRole("button", { name: "failed" }));
    await waitFor(() => expect(seen).toBe("failed"));
    expect(screen.getByRole("button", { name: "failed" })).toHaveAttribute("aria-pressed", "true");
  });

  it("list row updates from dashboard stream progress", async () => {
    setup("/jobs");
    await screen.findByText("#1");
    await waitFor(() => expect(streamFor("/jobs/stream")).toBeTruthy());
    act(() => streamFor("/jobs/stream").emit("progress", { job_id: 1, counters: { uploaded: 9 } }));
    act(() => streamFor("/jobs/stream").emit("phase", { id: 1, ts: "t", job_id: 1, name: "downloading" }));
    const row = (await screen.findByText("#1")).closest('[role="row"]') as HTMLElement;
    await waitFor(() => expect(within(row).getByText("9")).toBeInTheDocument());
    expect(within(row).getByText("downloading")).toBeInTheDocument();
  });
});

describe("job detail", () => {
  it("detail counters update from job stream", async () => {
    setup("/jobs/1");
    await screen.findByRole("heading", { name: "Job #1" });
    await waitFor(() => expect(streamFor("/jobs/1/stream")).toBeTruthy());
    act(() => streamFor("/jobs/1/stream").emit("progress", { job_id: 1, counters: { linked: 5 }, rate_bps: 2048 }));
    const tile = await screen.findByText("linked", { selector: "dt" });
    await waitFor(() => expect(tile.nextElementSibling).toHaveTextContent("5"));
    expect(screen.getByText("2.0 KB/s")).toBeInTheDocument();
  });

  it("indeterminate without total, determinate with total", async () => {
    setup("/jobs/1");
    const bar = await screen.findByRole("progressbar");
    expect(bar).not.toHaveAttribute("aria-valuenow");
    await waitFor(() => expect(streamFor("/jobs/1/stream")).toBeTruthy());
    act(() => streamFor("/jobs/1/stream").emit("progress", { job_id: 1, counters: { uploaded: 5 }, total: 10 }));
    await waitFor(() => expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "5"));
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "5 of 10 processed");
  });

  it("items table prepends live items without duplicates", async () => {
    setup("/jobs/1", {}, [{ id: 10, url: "https://a/old", outcome: "uploaded", reason: null, immich_asset_id: null }]);
    await screen.findByText("https://a/old");
    await waitFor(() => expect(streamFor("/jobs/1/stream")).toBeTruthy());
    const s = streamFor("/jobs/1/stream");
    act(() => {
      s.emit("item.uploaded", { id: 11, url: "https://a/new" });
      s.emit("item.uploaded", { id: 11, url: "https://a/new" });
      s.emit("item.uploaded", { id: 10, url: "https://a/old" });
    });
    await screen.findByText("https://a/new");
    expect(screen.getAllByText("https://a/new")).toHaveLength(1);
    expect(screen.getAllByText("https://a/old")).toHaveLength(1);
    const rows = screen.getAllByRole("row");
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.length).toBeLessThan(100);
  });

  it("thumbnail only for items with asset id and lazy", async () => {
    setup("/jobs/1", {}, [
      { id: 1, url: "https://a/1", outcome: "uploaded", reason: null, immich_asset_id: "abc" },
      { id: 2, url: "https://a/2", outcome: "failed", reason: "x", immich_asset_id: null },
    ]);
    await screen.findByText("https://a/2");
    const imgs = await waitFor(() => {
      const l = document.querySelectorAll("img");
      expect(l).toHaveLength(1);
      return l;
    });
    const img = imgs[0]!;
    expect(img).toHaveAttribute("loading", "lazy");
    expect(img).toHaveAttribute("src", "/api/v1/targets/7/assets/abc/thumbnail");
  });

  it("cancel confirms then posts", async () => {
    let posted = false;
    setup("/jobs/1");
    server.use(http.post("*/api/v1/jobs/1/cancel", () => { posted = true; return HttpResponse.json(job(1, { status: "cancelled" }), { status: 202 }); }));
    await user.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(posted).toBe(false);
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancel job" }));
    await waitFor(() => expect(posted).toBe(true));
  });

  it("retry hidden when no failures", async () => {
    setup("/jobs/1", { status: "succeeded", counters: { failed: 0 } });
    await screen.findByRole("button", { name: "Re-run" });
    expect(screen.queryByRole("button", { name: "Retry failed" })).toBeNull();
  });

  it("re-run navigates to new job", async () => {
    setup("/jobs/1", { status: "failed", counters: { failed: 2 } });
    server.use(
      http.post("*/api/v1/sources/3/run", () => HttpResponse.json(job(2), { status: 202 })),
      http.get("*/api/v1/jobs/2", () => HttpResponse.json(job(2))),
      http.get("*/api/v1/jobs/2/items", () => page([])),
    );
    expect(await screen.findByRole("button", { name: "Retry failed" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Re-run" }));
    expect(await screen.findByRole("heading", { name: "Job #2" })).toBeInTheDocument();
  });

  it("terminal status refetches detail and items", async () => {
    let detail = 0;
    let items = 0;
    setup("/jobs/1");
    server.use(
      http.get("*/api/v1/jobs/1", () => { detail++; return HttpResponse.json(job(1, detail > 1 ? { status: "succeeded", finished_at: "2026-10-26T10:05:00Z" } : {})); }),
      http.get("*/api/v1/jobs/1/items", () => { items++; return page([]); }),
    );
    await screen.findByRole("heading", { name: "Job #1" });
    await waitFor(() => expect(streamFor("/jobs/1/stream")).toBeTruthy());
    const d0 = detail, i0 = items;
    act(() => streamFor("/jobs/1/stream").emit("status", { job_id: 1, status: "succeeded" }));
    await waitFor(() => { expect(detail).toBeGreaterThan(d0); expect(items).toBeGreaterThan(i0); });
    expect(await screen.findByText(/5m 0s/)).toBeInTheDocument();
  });

  it("re-run 409 links to the active job", async () => {
    setup("/jobs/1", { status: "failed", counters: { failed: 0 } });
    server.use(http.post("*/api/v1/sources/3/run", () => HttpResponse.json({ detail: { msg: "active", job_id: 9 } }, { status: 409 })));
    await user.click(await screen.findByRole("button", { name: "Re-run" }));
    expect(await screen.findByRole("link", { name: /job #9/i })).toHaveAttribute("href", "/jobs/9");
  });

  it("retry 409 links to the active job", async () => {
    setup("/jobs/1", { status: "failed", counters: { failed: 2 } });
    server.use(http.post("*/api/v1/jobs/1/retry", () => HttpResponse.json({ detail: { msg: "active", job_id: 8 } }, { status: 409 })));
    await user.click(await screen.findByRole("button", { name: "Retry failed" }));
    expect(await screen.findByRole("link", { name: /job #8/i })).toHaveAttribute("href", "/jobs/8");
  });

  it("no thumbnails when the source is not visible", async () => {
    setup("/jobs/1", {}, [{ id: 1, url: "https://a/1", outcome: "uploaded", reason: null, immich_asset_id: "abc" }]);
    server.use(http.get("*/api/v1/sources/3", () => HttpResponse.json({ detail: "nope" }, { status: 404 })));
    await screen.findByText("https://a/1");
    expect(document.querySelectorAll("img")).toHaveLength(0);
  });

  it("thumbnail error falls back to placeholder", async () => {
    setup("/jobs/1", {}, [{ id: 1, url: "https://a/1", outcome: "uploaded", reason: null, immich_asset_id: "abc" }]);
    await waitFor(() => expect(document.querySelectorAll("img")).toHaveLength(1));
    act(() => { document.querySelector("img")!.dispatchEvent(new Event("error")); });
    await waitFor(() => expect(document.querySelectorAll("img")).toHaveLength(0));
  });
});
