import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeAll, describe, expect, it } from "vitest";
import type { MeOut } from "../../api/me";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";

const user = userEvent.setup({ delay: null });

const me: MeOut = { id: 1, name: "Own", email: "o@x.io", groups: [], role: "user" };
const c1 = { id: 1, name: "Pixiv", site: "pixiv.net", kind: "token", has_secret: true, owner_id: 1, visibility: "private", secret: "TOP-SECRET-VALUE", can_edit: true };
beforeAll(() => import("./CredentialsPage"), 30_000); // warm the lazy chunk
const open = () => renderWithProviders(null, { me, route: "/credentials" });

describe("credentials", () => {
  it("credential secret never rendered from API", async () => {
    server.use(http.get("*/api/v1/credentials", () => HttpResponse.json({ items: [c1], next_cursor: null })));
    const { container } = open();
    expect(await screen.findByText("Pixiv")).toBeInTheDocument();
    expect(screen.getByText("Secret saved")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit Pixiv" }));
    expect(screen.getByLabelText("Secret")).toHaveValue("");
    expect(document.body.innerHTML).not.toContain("TOP-SECRET-VALUE");
    expect(container.innerHTML).not.toContain("TOP-SECRET-VALUE");
  });

  it("cookies kind uses textarea", async () => {
    server.use(http.get("*/api/v1/credentials", () => HttpResponse.json({ items: [], next_cursor: null })));
    open();
    await user.click(await screen.findByRole("button", { name: "Add credential" }));
    expect(screen.getByLabelText("Secret").tagName).toBe("INPUT");
    await user.selectOptions(screen.getByLabelText("Kind"), "cookies");
    expect(screen.getByLabelText("Secret").tagName).toBe("TEXTAREA");
    await user.selectOptions(screen.getByLabelText("Kind"), "apprise");
    expect(screen.getByText("Apprise URL (e.g. ntfys://topic)")).toBeInTheDocument();
  });

  it("shows 422 on the secret field", async () => {
    server.use(
      http.get("*/api/v1/credentials", () => HttpResponse.json({ items: [], next_cursor: null })),
      http.post("*/api/v1/credentials", () =>
        HttpResponse.json({ detail: [{ loc: ["body", "secret"], msg: "bad token format", type: "value_error" }] }, { status: 422 }),
      ),
    );
    open();
    await user.click(await screen.findByRole("button", { name: "Add credential" }));
    await user.type(screen.getByLabelText("Name"), "n");
    await user.type(screen.getByLabelText("Site"), "s");
    await user.type(screen.getByLabelText("Secret"), "abc");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("bad token format")).toBeInTheDocument();
    expect(screen.getByLabelText("Secret")).toHaveAttribute("aria-invalid", "true");
  });

  it("non-owner without edit sees no Edit, Delete or Share", async () => {
    server.use(http.get("*/api/v1/credentials", () => HttpResponse.json({ items: [{ ...c1, can_edit: false }], next_cursor: null })));
    renderWithProviders(null, { me: { ...me, id: 2 }, route: "/credentials" });
    expect(await screen.findByText("Pixiv")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit Pixiv" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete Pixiv" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Share Home" })).not.toBeInTheDocument();
  });

  it("edit-share user sees Edit only", async () => {
    server.use(http.get("*/api/v1/credentials", () => HttpResponse.json({ items: [c1], next_cursor: null })));
    renderWithProviders(null, { me: { ...me, id: 2 }, route: "/credentials" });
    expect(await screen.findByRole("button", { name: "Edit Pixiv" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete Pixiv" })).not.toBeInTheDocument();
  });

  it("shows server message for rejected apprise host", async () => {
    server.use(
      http.get("*/api/v1/credentials", () => HttpResponse.json({ items: [], next_cursor: null })),
      http.post("*/api/v1/credentials", () => HttpResponse.json({ detail: "Private host not allowed" }, { status: 422 })),
    );
    open();
    await user.click(await screen.findByRole("button", { name: "Add credential" }));
    await user.type(screen.getByLabelText("Name"), "n");
    await user.type(screen.getByLabelText("Site"), "s");
    await user.selectOptions(screen.getByLabelText("Kind"), "apprise");
    await user.type(screen.getByLabelText("Secret"), "json://10.0.0.1");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Private host not allowed")).toBeInTheDocument();
  });
});
