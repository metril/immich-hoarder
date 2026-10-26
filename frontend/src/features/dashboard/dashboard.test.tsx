import { act, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { failedLabel, failedLast24h } from "./hooks";
import type { MeOut } from "../../api/me";
import { renderWithProviders } from "../../test/render";
import { dashboardDefaults } from "../../test/handlers";
import { server } from "../../test/server";
import { FakeEventSource } from "../../test/setup";

const me: MeOut = { id: 1, name: "Own", email: "o@x.io", groups: [], role: "user" };
const job = (id: number, status: string, o: Record<string, unknown> = {}) => ({
  id, status, counters: { uploaded: 2 }, phase: null, source_id: 3, source_name: "Cats",
  created_at: "2026-10-26T10:00:00Z", started_at: "2026-10-26T10:00:00Z", finished_at: null, error: null, log_level: null, triggered_by: 1, ...o,
});
const upload = (id: number) => ({ id, url: `https://x.io/pics/cat${id}.jpg`, outcome: "uploaded", immich_asset_id: `a${id}`, job_id: 1, source_id: 3, target_id: 7, created_at: null });
const page = (items: unknown[], next: string | null = null) => HttpResponse.json({ items, next_cursor: next });

function setup(opts: { jobs?: unknown[]; uploads?: unknown[]; sources?: unknown[]; next?: string | null } = {}) {
  server.use(...dashboardDefaults);
  server.use(
    http.get("*/api/v1/jobs", ({ request }) => {
      const s = new URL(request.url).searchParams.get("status");
      return page((opts.jobs ?? [job(1, "running")]).filter((j) => (j as { status: string }).status === s));
    }),
    http.get("*/api/v1/sources", () => page(opts.sources ?? [{ id: 3, name: "Cats", target_id: 7 }])),
    http.get("*/api/v1/uploads", () => page(opts.uploads ?? [], opts.next ?? null)),
  );
  return renderWithProviders(null, { me, route: "/" });
}
const stream = () => FakeEventSource.instances.filter((e) => e.url.includes("/jobs/stream")).at(-1)!;

describe("dashboard", () => {
  it("live jobs update counters from stream", async () => {
    setup();
    const link = await screen.findByRole("link", { name: "#1" }, { timeout: 5000 });
    expect(link).toHaveAttribute("href", "/jobs/1");
    await waitFor(() => expect(stream()).toBeTruthy());
    act(() => stream().emit("progress", { job_id: 1, counters: { uploaded: 9 } }));
    const card = link.closest("li") as HTMLElement;
    await waitFor(() => expect(within(card).getByText("9")).toBeInTheDocument());
  });

  it("gallery images lazy except first six", async () => {
    setup({ uploads: Array.from({ length: 8 }, (_, i) => upload(i + 1)) });
    const imgs = await screen.findAllByRole("img");
    expect(imgs).toHaveLength(8);
    imgs.forEach((img, i) => {
      expect(img).toHaveAttribute("width");
      expect(img).toHaveAttribute("height");
      expect(img).toHaveAttribute("alt", `cat${i + 1}.jpg`);
      if (i < 6) {
        expect(img).not.toHaveAttribute("loading");
        expect(img).toHaveAttribute("fetchpriority", "high");
      } else {
        expect(img).toHaveAttribute("loading", "lazy");
      }
    });
  });

  it("gallery refetches on uploads invalidation", async () => {
    let n = 0;
    setup();
    server.use(http.get("*/api/v1/uploads", () => { n += 1; return page([upload(n)]); }));
    await screen.findByRole("img", { name: "cat1.jpg" });
    await waitFor(() => expect(stream()).toBeTruthy());
    act(() => stream().emit("status", { id: 5, ts: "t", job_id: 1, status: "succeeded" }));
    expect(await screen.findByRole("img", { name: "cat2.jpg" })).toBeInTheDocument();
  });

  it("empty states render", async () => {
    setup({ jobs: [] });
    expect(await screen.findByText("No jobs running")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Run a source" })).toBeInTheDocument();
    expect(await screen.findByText("No uploads yet")).toBeInTheDocument();
  });

  it("hides run button without sources and shows tiles", async () => {
    setup({ jobs: [], sources: [] });
    await screen.findByText("No jobs running");
    expect(screen.queryByRole("link", { name: "Run a source" })).toBeNull();
    expect(screen.getByText("Failed (24 h)")).toBeInTheDocument();
  });
});

describe("dashboard states and edge cases", () => {
  it("queued job that starts moves tiles without duplicate rows", async () => {
    setup({ jobs: [job(1, "queued")] });
    const link = await screen.findByRole("link", { name: "#1" });
    const tile = (l: string) => screen.getByText(l).parentElement as HTMLElement;
    await waitFor(() => expect(within(tile("Queued")).getByText("1")).toBeInTheDocument());
    // Server now reports the job running in both lists (mid-transition).
    server.use(http.get("*/api/v1/jobs", ({ request }) => {
      const s = new URL(request.url).searchParams.get("status");
      return page(s === "running" || s === "queued" ? [job(1, "running")] : []);
    }));
    await waitFor(() => expect(stream()).toBeTruthy());
    act(() => stream().emit("status", { id: 3, ts: "t", job_id: 1, status: "running" }));
    await waitFor(() => expect(within(tile("Running")).getByText("1")).toBeInTheDocument());
    expect(within(tile("Queued")).getByText("0")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "#1" })).toHaveLength(1);
    expect(link).toBeTruthy();
  });

  it("shows skeletons while pending", async () => {
    setup();
    server.use(
      http.get("*/api/v1/jobs", () => new Promise(() => {})),
      http.get("*/api/v1/uploads", () => new Promise(() => {})),
    );
    expect(await screen.findByRole("status", { name: "Loading jobs" })).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Loading Running" })).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Loading uploads" })).toBeInTheDocument();
    expect(screen.queryByText("No jobs running")).toBeNull();
  });

  it("shows error state with retry for jobs and uploads", async () => {
    let fail = true;
    setup();
    server.use(
      http.get("*/api/v1/jobs", () => (fail ? new HttpResponse(null, { status: 500 }) : page([]))),
      http.get("*/api/v1/uploads", () => (fail ? new HttpResponse(null, { status: 500 }) : page([upload(1)]))),
    );
    await waitFor(() => expect(screen.getAllByRole("alert")).toHaveLength(2), { timeout: 5000 });
    fail = false;
    for (const b of screen.getAllByRole("button", { name: "Retry" })) await userEvent.click(b);
    expect(await screen.findByText("No jobs running")).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: "cat1.jpg" })).toBeInTheDocument();
  });

  it("image error falls back to placeholder", async () => {
    setup({ uploads: [upload(1)] });
    const img = await screen.findByRole("img", { name: "cat1.jpg" });
    act(() => { img.dispatchEvent(new Event("error")); });
    await waitFor(() => expect(screen.getByRole("img", { name: "cat1.jpg" }).tagName).toBe("SPAN"));
  });

  it("load more fetches next page by cursor", async () => {
    let cursor: string | null = null;
    setup();
    server.use(http.get("*/api/v1/uploads", ({ request }) => {
      cursor = new URL(request.url).searchParams.get("cursor");
      return cursor ? page([upload(2)]) : page([upload(1)], "c1");
    }));
    await screen.findByRole("img", { name: "cat1.jpg" });
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByRole("img", { name: "cat2.jpg" })).toBeInTheDocument();
    expect(cursor).toBe("c1");
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
  });

  it("clicking an image opens preview dialog", async () => {
    setup({ uploads: [upload(1)] });
    await userEvent.click(await screen.findByRole("button", { name: "Preview cat1.jpg" }));
    const dlg = await screen.findByRole("dialog");
    expect(within(dlg).getByRole("img", { name: "cat1.jpg" }).getAttribute("src")).toContain("size=preview");
    await userEvent.click(within(dlg).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});

describe("failed tile helpers", () => {
  const now = new Date("2026-10-26T12:00:00Z").getTime();
  const recent = { finished_at: "2026-10-26T10:00:00Z", created_at: "2026-10-26T09:00:00Z" };
  const old = { finished_at: "2026-10-20T10:00:00Z", created_at: "2026-10-20T09:00:00Z" };
  it("excludes old failures", () => expect(failedLast24h([recent, old], now)).toBe(1));
  it("adds + only when more pages and all loaded are recent", () => {
    expect(failedLabel([recent, recent], true, now)).toBe("2+");
    expect(failedLabel([recent, old], true, now)).toBe("1");
    expect(failedLabel([recent], false, now)).toBe("1");
  });
});
