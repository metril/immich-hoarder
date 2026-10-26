import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { MeOut } from "../../api/me";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
const me: MeOut = { id: 1, name: "Own", email: "o@x.io", groups: [], role: "user" };
const t1 = { id: 1, name: "Home", url: "https://immich.example", has_api_key: true, owner_id: 1, visibility: "private" };

beforeAll(() => import("./TargetsPage"), 30_000); // warm the lazy chunk
const open = () => renderWithProviders(null, { me, route: "/targets" });

describe("targets", () => {
  it("creates target and shows in list", async () => {
    let items: unknown[] = [];
    let body: Record<string, unknown> = {};
    server.use(
      http.get("*/api/v1/targets", () => HttpResponse.json({ items, next_cursor: null })),
      http.post("*/api/v1/targets", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        items = [{ ...t1, name: "New" }];
        const created = { ...t1, name: "New" };
        return HttpResponse.json(created, { status: 201 });
      }),
    );
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Add target" }));
    await userEvent.type(screen.getByLabelText("Name"), "New");
    await userEvent.type(screen.getByLabelText("URL"), "https://immich.example");
    await userEvent.type(screen.getByLabelText("API key"), "k123");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("API key saved")).toBeInTheDocument();
    expect(body).toMatchObject({ name: "New", url: "https://immich.example", api_key: "k123", visibility: "private" });
  });

  it("edit omits empty api_key from PATCH", async () => {
    let body: Record<string, unknown> | undefined;
    server.use(
      http.get("*/api/v1/targets", () => HttpResponse.json({ items: [t1], next_cursor: null })),
      http.patch("*/api/v1/targets/1", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(t1);
      }),
    );
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Edit Home" }));
    const name = screen.getByLabelText("Name");
    await userEvent.clear(name);
    await userEvent.type(name, "Renamed");
    expect(screen.getByLabelText("API key")).toHaveValue("");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(body).toBeDefined());
    expect(body).toEqual({ name: "Renamed", url: "https://immich.example" });
  });

  it("test button shows missing permissions", async () => {
    server.use(
      http.get("*/api/v1/targets", () => HttpResponse.json({ items: [t1], next_cursor: null })),
      http.post("*/api/v1/targets/1/test", () =>
        HttpResponse.json({ ok: false, error: "Forbidden", missing_permissions: ["asset.upload", "album.read"] }),
      ),
    );
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Test Home" }));
    const dlg = await screen.findByRole("dialog");
    expect(within(dlg).getByText("Forbidden")).toBeInTheDocument();
    expect(within(dlg).getByText("asset.upload")).toBeInTheDocument();
    expect(within(dlg).getByText("album.read")).toBeInTheDocument();
  });

  it("delete is optimistic and rolls back on 403", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => (release = r));
    server.use(
      http.get("*/api/v1/targets", () => HttpResponse.json({ items: [t1], next_cursor: null })),
      http.delete("*/api/v1/targets/1", async () => {
        await gate;
        return HttpResponse.json({ detail: "forbidden" }, { status: 403 });
      }),
    );
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Delete Home" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.queryByText("https://immich.example")).not.toBeInTheDocument());
    release();
    expect(await screen.findByText("https://immich.example")).toBeInTheDocument();
  });
});
