import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse, delay } from "msw";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { MeOut } from "../../api/me";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";
import type { SourceOut } from "./hooks";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
const me: MeOut = { id: 1, name: "Own", email: "o@x.io", groups: [], role: "user" };
const s3 = {
  id: 3, name: "Cats", url: "https://example.com/cats", extractor: "reddit", target_id: 1, credential_id: null, album_template: "",
  schedule_cron: "0 3 * * *", backfill_mode: "full", backfill_value: null, allow_animated: false, filters: { phash_distance: 3 }, notify: { credential_ids: [], on: ["failure"] },
  gdl_options: {}, proxy: null, log_level: null, enabled: false, ephemeral: false, visibility: "private", owner_id: 1, can_edit: true,
} as SourceOut;
const target = { id: 1, name: "Home", url: "https://immich.example", has_api_key: true, owner_id: 1, visibility: "private", can_edit: true, can_use: true };

beforeAll(() => Promise.all([import("./SourcesPage"), import("./SourceForm")]), 30_000);

function setup(route = "/sources", sources: unknown[] = [s3]) {
  server.use(
    http.get("*/api/v1/sources", () => HttpResponse.json({ items: sources, next_cursor: null })),
    http.get("*/api/v1/sources/3", () => HttpResponse.json(s3)),
    http.get("*/api/v1/targets", () => HttpResponse.json({ items: [target], next_cursor: null })),
    http.get("*/api/v1/credentials", () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get("*/api/v1/extractors", () => HttpResponse.json([])),
  );
  return renderWithProviders(null, { me, route });
}

describe("sources page", () => {
  it("lists sources with target name and schedule", async () => {
    setup();
    expect(await screen.findByText("Cats")).toBeInTheDocument();
    expect(await screen.findByText("Home")).toBeInTheDocument();
    expect(screen.getByText(/03:00/)).toBeInTheDocument();
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
    await userEvent.click(sw);
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
    await userEvent.keyboard("n");
    expect(await screen.findByRole("heading", { name: "New source" })).toBeInTheDocument();
  });

  it("delete conflict surfaces the server message", async () => {
    const { toast } = await import("sonner");
    setup();
    server.use(http.delete("*/api/v1/sources/3", () => HttpResponse.json({ detail: "source has an active job" }, { status: 409 })));
    await userEvent.click(await screen.findByRole("button", { name: "Delete Cats" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("source has an active job"));
  });
});
