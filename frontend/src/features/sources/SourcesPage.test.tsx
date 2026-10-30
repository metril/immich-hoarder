import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse, delay } from "msw";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { keys } from "../../api/keys";
import type { MeOut } from "../../api/me";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";
import type { SourceOut } from "./hooks";

const user = userEvent.setup({ delay: null });

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
const me: MeOut = { id: 1, name: "Own", email: "o@x.io", groups: [], role: "user", must_change_password: false };
const s3 = {
  id: 3, name: "Cats", url: "https://example.com/cats", extractor: "reddit", target_id: 1, credential_id: null, album_template: "",
  schedule_cron: "0 3 * * *", backfill_mode: "full", backfill_value: null, allow_animated: false, reupload_deleted: false, filters: { phash_distance: 3 }, notify: { credential_ids: [], on: ["failure"] },
  gdl_options: {}, proxy: null, log_level: null, enabled: false, ephemeral: false, visibility: "private", owner_id: 1, can_edit: true, can_use: true,
} as SourceOut;
const target = { id: 1, name: "Home", url: "https://immich.example", has_api_key: true, owner_id: 1, visibility: "private", can_edit: true, can_use: true };

beforeAll(() => Promise.all([import("./SourcesPage"), import("./SourceForm")]), 30_000);

function setup(route = "/sources", sources: unknown[] = [s3]) {
  server.use(
    http.get("*/api/v1/sources", () => HttpResponse.json({ items: sources, next_cursor: null })),
    http.get("*/api/v1/sources/3", () => HttpResponse.json(s3)),
    http.get("*/api/v1/targets", () => HttpResponse.json({ items: [target], next_cursor: null })),
    http.get("*/api/v1/credentials", () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get("*/api/v1/extractors", () => HttpResponse.json({ items: [] })),
  );
  return renderWithProviders(null, { me, route });
}

describe("sources page", () => {
  it("lists sources with target name and schedule", async () => {
    vi.spyOn(Date.prototype, "getTimezoneOffset").mockReturnValue(0);
    setup();
    expect(await screen.findByText("Cats")).toBeInTheDocument();
    expect(await screen.findByText("Home")).toBeInTheDocument();
    expect(await screen.findByText(/03:00/)).toBeInTheDocument();
  });

  it("describes the schedule in local time (cron is stored as UTC)", async () => {
    vi.spyOn(Date.prototype, "getTimezoneOffset").mockReturnValue(300); // UTC-5
    setup();
    expect(await screen.findByText("Cats")).toBeInTheDocument();
    // "0 3 * * *" UTC is 22:00 the previous day at UTC-5
    const el = await screen.findByText(/22:00/);
    expect(el).toBeInTheDocument();
    expect(el.closest("[title]")?.getAttribute("title")).toBe("0 3 * * * (UTC)");
  });

  it("enabled switch is optimistic", async () => {
    let body: unknown;
    setup();
    server.use(
      http.patch("*/api/v1/sources/3", async ({ request }) => {
        body = await request.json();
        await delay(300);
        return HttpResponse.json({ ...s3, enabled: true });
      }),
    );
    const sw = await screen.findByRole("switch", { name: "Enabled Cats" });
    expect(sw).toHaveAttribute("aria-checked", "false");
    await user.click(sw);
    expect(screen.getByRole("switch", { name: "Enabled Cats" })).toHaveAttribute("aria-checked", "true");
    await waitFor(() => expect(body).toEqual({ enabled: true }));
  });

  it("?edit=3 opens sheet with source 3", async () => {
    setup("/sources?edit=3");
    expect(await screen.findByRole("heading", { name: "Edit Cats" })).toBeInTheDocument();
    expect(await screen.findByLabelText("Name")).toHaveValue("Cats");
  });

  it("n opens new source sheet", async () => {
    setup();
    await screen.findByText("Cats");
    await user.keyboard("n");
    expect(await screen.findByRole("heading", { name: "New source" })).toBeInTheDocument();
  });

  it("delete conflict surfaces the server message", async () => {
    const { toast } = await import("sonner");
    setup();
    server.use(http.delete("*/api/v1/sources/3", () => HttpResponse.json({ detail: "source has an active job" }, { status: 409 })));
    await user.click(await screen.findByRole("button", { name: "More actions for Cats" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete Cats" }));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("source has an active job"));
  });

  it("new-source sheet dry-runs the unsaved draft", async () => {
    let body: Record<string, unknown> = {};
    setup("/sources?new=1");
    server.use(
      http.post("*/api/v1/sources/preview", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ items: [{ url: "https://e.com/a.jpg", title: "A", date: null, filename: "a.jpg", verdict: null }] });
      }),
    );
    await user.type(await screen.findByLabelText("Name"), "Draft");
    await user.type(screen.getByLabelText("URL"), "https://example.com/draft");
    await screen.findByRole("option", { name: "Home" });
    await user.selectOptions(screen.getByLabelText("Target"), "1");
    const region = screen.getByRole("region", { name: "Dry run" });
    await user.click(await within(region).findByRole("button", { name: "Dry run" }));
    expect(await within(region).findByText("would grab")).toBeInTheDocument();
    expect(body).toMatchObject({ name: "Draft", url: "https://example.com/draft", target_id: 1, limit: 50 });
  });

  it("hides Run when the source is not usable", async () => {
    setup("/sources", [{ ...s3, can_use: false }]);
    await screen.findByText("Cats");
    expect(screen.queryByRole("button", { name: "Run Cats" })).not.toBeInTheDocument();
  });

  it("shows Run when usable", async () => {
    setup();
    expect(await screen.findByRole("button", { name: "Run Cats" })).toBeInTheDocument();
  });

  it("delete invalidates jobs lists and the source detail", async () => {
    const { queryClient } = setup();
    server.use(http.delete("*/api/v1/sources/3", () => new HttpResponse(null, { status: 204 })));
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    await user.click(await screen.findByRole("button", { name: "More actions for Cats" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete Cats" }));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => {
      const ks = spy.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
      expect(ks).toContain(JSON.stringify(["list", "jobs"]));
      expect(ks).toContain(JSON.stringify(keys.detail("sources", 3)));
    });
  });

  it("forget seen URLs confirms in-page, toasts the count and invalidates", async () => {
    const { toast } = await import("sonner");
    const { queryClient } = setup();
    server.use(http.post("*/api/v1/sources/3/forget-seen", () => HttpResponse.json({ forgotten: 7 })));
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    await user.click(await screen.findByRole("button", { name: "More actions for Cats" }));
    await user.click(screen.getByRole("menuitem", { name: "Forget seen URLs for Cats" }));
    await user.click(screen.getByRole("button", { name: "Forget" }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Forgot 7 seen URLs"));
    const ks = spy.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
    expect(ks).toContain(JSON.stringify(["list", "jobs"]));
  });
});
