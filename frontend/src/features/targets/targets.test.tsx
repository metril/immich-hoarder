import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { MeOut } from "../../api/me";
import { toast } from "sonner";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
const me: MeOut = { id: 1, name: "Own", email: "o@x.io", groups: [], role: "user" };
const t1 = { id: 1, name: "Home", url: "https://immich.example", has_api_key: true, owner_id: 1, visibility: "private", can_edit: true };

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
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
  });

  it("edit-share user sees Edit but not Delete or Share", async () => {
    const other: MeOut = { ...me, id: 2 };
    server.use(http.get("*/api/v1/targets", () => HttpResponse.json({ items: [t1], next_cursor: null })));
    renderWithProviders(null, { me: other, route: "/targets" });
    expect(await screen.findByRole("button", { name: "Edit Home" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete Home" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Share" })).not.toBeInTheDocument();
  });

  it("use-share user sees only Test and Albums; admin sees all", async () => {
    server.use(http.get("*/api/v1/targets", () => HttpResponse.json({ items: [{ ...t1, can_edit: false }], next_cursor: null })));
    const { unmount } = renderWithProviders(null, { me: { ...me, id: 2 }, route: "/targets" });
    expect(await screen.findByRole("button", { name: "Test Home" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit Home" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete Home" })).not.toBeInTheDocument();
    unmount();
    renderWithProviders(null, { me: { ...me, id: 3, role: "admin" }, route: "/targets" });
    expect(await screen.findByRole("button", { name: "Delete Home" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Share" })).toBeInTheDocument();
  });

  it("shows 422 on the url field", async () => {
    server.use(
      http.get("*/api/v1/targets", () => HttpResponse.json({ items: [], next_cursor: null })),
      http.post("*/api/v1/targets", () =>
        HttpResponse.json({ detail: [{ loc: ["body", "url"], msg: "unreachable host", type: "value_error" }] }, { status: 422 }),
      ),
    );
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Add target" }));
    await userEvent.type(screen.getByLabelText("Name"), "N");
    await userEvent.type(screen.getByLabelText("URL"), "https://x.example");
    await userEvent.type(screen.getByLabelText("API key"), "k");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("unreachable host")).toBeInTheDocument();
    expect(screen.getByLabelText("URL")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Name")).toHaveValue("N");
  });

  it("test dialog returns focus to the Test button", async () => {
    server.use(
      http.get("*/api/v1/targets", () => HttpResponse.json({ items: [t1], next_cursor: null })),
      http.post("*/api/v1/targets/1/test", () => HttpResponse.json({ ok: true, version: "1.2", missing_permissions: [] })),
    );
    open();
    const b = await screen.findByRole("button", { name: "Test Home" });
    await userEvent.click(b);
    expect(await screen.findByText("Connected · Immich v1.2")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(b).toHaveFocus());
  });
});
