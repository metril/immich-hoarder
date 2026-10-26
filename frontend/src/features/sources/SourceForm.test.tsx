import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { SourceForm } from "./SourceForm";
import type { SourceOut } from "./hooks";

const user = userEvent.setup({ delay: null });

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const hidden = { id: 4, name: "Locked", url: "https://l.x", has_api_key: true, owner_id: 2, visibility: "restricted", can_edit: false, can_use: false };
const target = { id: 3, name: "Home", url: "https://i.x", has_api_key: true, owner_id: 1, visibility: "private", can_edit: true, can_use: true };
const creds = [
  { id: 10, name: "Discord", kind: "apprise", owner_id: 1, visibility: "private", can_edit: true, has_secret: true, can_use: true },
  { id: 11, name: "Reddit login", kind: "gallery_dl", owner_id: 1, visibility: "private", can_edit: true, has_secret: true, can_use: true },
  { id: 12, name: "Unusable apprise", kind: "apprise", owner_id: 2, visibility: "private", can_edit: false, has_secret: true, can_use: false },
];
const src: SourceOut = {
  id: 7, name: "Cats", url: "https://reddit.com/r/cats", target_id: 3, credential_id: null, album_template: "{subreddit}",
  schedule_cron: null, backfill_mode: "full", backfill_value: null, allow_animated: false,
  filters: { phash_distance: 3 }, notify: { credential_ids: [], on: ["failure"] }, gdl_options: {}, proxy: null, log_level: null,
  enabled: true, ephemeral: false, extractor: "reddit", owner_id: 1, visibility: "private", can_edit: true, can_use: true,
};

function handlers() {
  server.use(
    http.get("*/api/v1/targets", () => HttpResponse.json({ items: [target], next_cursor: null })),
    http.get("*/api/v1/credentials", () => HttpResponse.json({ items: creds, next_cursor: null })),
    http.get("*/api/v1/extractors", () => HttpResponse.json({ items: [{ category: "reddit", subcategories: [] }] })),
  );
}

describe("SourceForm", () => {
  it("last_n requires integer", async () => {
    handlers();
    const onSaved = vi.fn();
    renderWithProviders(<SourceForm onSaved={onSaved} />);
    await user.type(await screen.findByLabelText("Name"), "S");
    await user.type(screen.getByLabelText("URL"), "https://reddit.com/r/x");
    await user.selectOptions(await screen.findByLabelText("Target"), "3");
    await user.click(screen.getByLabelText("Last N items"));
    await user.type(screen.getByLabelText("Item count"), "0");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Enter a whole number, 1 or more")).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("notify lists only apprise credentials", async () => {
    handlers();
    renderWithProviders(<SourceForm onSaved={vi.fn()} />);
    expect(await screen.findByLabelText("Discord")).toBeInTheDocument();
    expect(screen.queryByLabelText("Reddit login")).not.toBeInTheDocument();
  });

  it("edit sends only dirty fields", async () => {
    handlers();
    let body: unknown;
    server.use(
      http.patch("*/api/v1/sources/7", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(src);
      }),
    );
    renderWithProviders(<SourceForm initial={src} onSaved={vi.fn()} />);
    await screen.findByRole("option", { name: "Home" });
    const name = await screen.findByLabelText("Name");
    await user.clear(name);
    await user.type(name, "Dogs");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(body).toBeDefined());
    expect(body).toEqual({ name: "Dogs" });
  });

  it("server 422 on schedule_cron shows under cron field", async () => {
    handlers();
    server.use(
      http.patch("*/api/v1/sources/7", () =>
        HttpResponse.json({ detail: [{ loc: ["body", "schedule_cron"], msg: "invalid cron expression", type: "value_error" }] }, { status: 422 }),
      ),
    );
    renderWithProviders(<SourceForm initial={src} onSaved={vi.fn()} />);
    await screen.findByRole("option", { name: "Home" });
    await user.selectOptions(screen.getByLabelText("Frequency"), "hourly");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("invalid cron expression")).toBeInTheDocument();
    expect(screen.getByLabelText("Frequency")).toHaveValue("hourly");
  });

  it("pickers list only usable items; credential select excludes apprise", async () => {
    handlers();
    server.use(http.get("*/api/v1/targets", () => HttpResponse.json({ items: [target, hidden], next_cursor: null })));
    renderWithProviders(<SourceForm onSaved={vi.fn()} />);
    await screen.findByRole("option", { name: "Home" });
    expect(screen.queryByRole("option", { name: "Locked" })).not.toBeInTheDocument();
    const cred = screen.getByLabelText("Credential");
    expect(within(cred).getByRole("option", { name: "Reddit login" })).toBeInTheDocument();
    expect(within(cred).queryByRole("option", { name: "Discord" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Unusable apprise")).not.toBeInTheDocument();
  });

  it("pickers load every page", async () => {
    handlers();
    const t2 = { ...target, id: 5, name: "Second page" };
    server.use(
      http.get("*/api/v1/targets", ({ request }) =>
        new URL(request.url).searchParams.get("cursor")
          ? HttpResponse.json({ items: [t2], next_cursor: null })
          : HttpResponse.json({ items: [target], next_cursor: "c2" }),
      ),
    );
    renderWithProviders(<SourceForm onSaved={vi.fn()} />);
    expect(await screen.findByRole("option", { name: "Second page" })).toBeInTheDocument();
  });

  it("create POST body has numeric target_id and null backfill_value for full", async () => {
    handlers();
    let body: Record<string, unknown> = {};
    server.use(
      http.post("*/api/v1/sources", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(src, { status: 201 });
      }),
    );
    renderWithProviders(<SourceForm onSaved={vi.fn()} />);
    await user.type(await screen.findByLabelText("Name"), "S");
    await user.type(screen.getByLabelText("URL"), "https://reddit.com/r/x");
    await user.selectOptions(await screen.findByLabelText("Target"), "3");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(body.name).toBe("S"));
    expect(body).toMatchObject({ target_id: 3, backfill_mode: "full", backfill_value: null, credential_id: null, visibility: "private" });
  });

  it("edit filter change sends only filters", async () => {
    handlers();
    let body: unknown;
    server.use(
      http.patch("*/api/v1/sources/7", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(src);
      }),
    );
    renderWithProviders(<SourceForm initial={src} onSaved={vi.fn()} />);
    await screen.findByRole("option", { name: "Home" });
    await user.type(screen.getByLabelText("Min width (px)"), "800");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(body).toBeDefined());
    expect(Object.keys(body as object)).toEqual(["filters"]);
    expect((body as { filters: { min_width: number } }).filters.min_width).toBe(800);
  });

  it("server 422 at filters shows as a filters root error", async () => {
    handlers();
    server.use(
      http.patch("*/api/v1/sources/7", () =>
        HttpResponse.json({ detail: [{ loc: ["body", "filters"], msg: "min_bytes must be <= max_bytes", type: "value_error" }] }, { status: 422 }),
      ),
    );
    renderWithProviders(<SourceForm initial={src} onSaved={vi.fn()} />);
    await screen.findByRole("option", { name: "Home" });
    await user.type(screen.getByLabelText("Min width (px)"), "800");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("min_bytes must be <= max_bytes")).toBeInTheDocument();
    expect(screen.getByLabelText("Min width (px)")).toHaveValue(800);
  });

  it("notify errors are described by the fieldset", async () => {
    handlers();
    server.use(
      http.patch("*/api/v1/sources/7", () =>
        HttpResponse.json({ detail: [{ loc: ["body", "notify"], msg: "bad notify", type: "value_error" }] }, { status: 422 }),
      ),
    );
    renderWithProviders(<SourceForm initial={src} onSaved={vi.fn()} />);
    await screen.findByRole("option", { name: "Home" });
    await user.click(await screen.findByLabelText("On success"));
    await user.click(screen.getByRole("button", { name: "Save" }));
    const msg = await screen.findByText("bad notify");
    expect(screen.getByRole("group", { name: "Notifications" })).toHaveAttribute("aria-describedby", msg.id);
  });
});
