import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { SourceForm } from "./SourceForm";
import type { SourceOut } from "./hooks";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const target = { id: 3, name: "Home", url: "https://i.x", has_api_key: true, owner_id: 1, visibility: "private", can_edit: true };
const creds = [
  { id: 10, name: "Discord", kind: "apprise", owner_id: 1, visibility: "private", can_edit: true, has_secret: true },
  { id: 11, name: "Reddit login", kind: "gallery_dl", owner_id: 1, visibility: "private", can_edit: true, has_secret: true },
];
const src: SourceOut = {
  id: 7, name: "Cats", url: "https://reddit.com/r/cats", target_id: 3, credential_id: null, album_template: "{subreddit}",
  schedule_cron: null, backfill_mode: "full", backfill_value: null, allow_animated: false,
  filters: { phash_distance: 3 }, notify: { credential_ids: [], on: ["failure"] }, gdl_options: {}, proxy: null, log_level: null,
  enabled: true, ephemeral: false, extractor: "reddit", owner_id: 1, visibility: "private", can_edit: true,
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
    await userEvent.type(await screen.findByLabelText("Name"), "S");
    await userEvent.type(screen.getByLabelText("URL"), "https://reddit.com/r/x");
    await userEvent.selectOptions(await screen.findByLabelText("Target"), "3");
    await userEvent.click(screen.getByLabelText("Last N items"));
    await userEvent.type(screen.getByLabelText("Item count"), "0");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
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
    await userEvent.clear(name);
    await userEvent.type(name, "Dogs");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
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
    await userEvent.click(screen.getByRole("button", { name: "Hourly" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const input = screen.getByLabelText("Schedule (cron)");
    await waitFor(() => expect(input).toHaveAttribute("aria-invalid", "true"));
    expect(screen.getByText("invalid cron expression")).toBeInTheDocument();
    expect(input).toHaveValue("0 * * * *");
  });
});
