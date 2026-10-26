import { act, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeAll, describe, expect, it } from "vitest";
import type { MeOut } from "../../api/me";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { FakeEventSource } from "../../test/setup";

const me: MeOut = { id: 1, name: "Own", email: "o@x.io", groups: [], role: "user" };
const job = (id: number, status: string, o: Record<string, unknown> = {}) => ({
  id, status, counters: { uploaded: 2 }, phase: null, source_id: 3, source_name: "Cats",
  created_at: "2026-10-26T10:00:00Z", started_at: "2026-10-26T10:00:00Z", finished_at: null, error: null, log_level: null, triggered_by: 1, ...o,
});
const upload = (id: number) => ({ id, url: `https://x.io/pics/cat${id}.jpg`, outcome: "uploaded", immich_asset_id: `a${id}`, job_id: 1, source_id: 3, target_id: 7, created_at: null });
const page = (items: unknown[], next: string | null = null) => HttpResponse.json({ items, next_cursor: next });

beforeAll(() => import("./Dashboard"), 30_000);

function setup(opts: { jobs?: unknown[]; uploads?: unknown[]; sources?: unknown[]; next?: string | null } = {}) {
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
    const link = await screen.findByRole("link", { name: "#1" });
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
