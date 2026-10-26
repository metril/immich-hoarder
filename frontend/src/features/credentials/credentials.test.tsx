import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeAll, describe, expect, it } from "vitest";
import type { MeOut } from "../../api/me";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";

const me: MeOut = { id: 1, name: "Own", email: "o@x.io", groups: [], role: "user" };
const c1 = { id: 1, name: "Pixiv", site: "pixiv.net", kind: "token", has_secret: true, owner_id: 1, visibility: "private", secret: "TOP-SECRET-VALUE" };
beforeAll(() => import("./CredentialsPage"), 30_000); // warm the lazy chunk
const open = () => renderWithProviders(null, { me, route: "/credentials" });

describe("credentials", () => {
  it("credential secret never rendered from API", async () => {
    server.use(http.get("*/api/v1/credentials", () => HttpResponse.json({ items: [c1], next_cursor: null })));
    const { container } = open();
    expect(await screen.findByText("Pixiv")).toBeInTheDocument();
    expect(screen.getByText("Secret saved")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Edit Pixiv" }));
    expect(screen.getByLabelText("Secret")).toHaveValue("");
    expect(document.body.innerHTML).not.toContain("TOP-SECRET-VALUE");
    expect(container.innerHTML).not.toContain("TOP-SECRET-VALUE");
  });

  it("cookies kind uses textarea", async () => {
    server.use(http.get("*/api/v1/credentials", () => HttpResponse.json({ items: [], next_cursor: null })));
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Add credential" }));
    expect(screen.getByLabelText("Secret").tagName).toBe("INPUT");
    await userEvent.selectOptions(screen.getByLabelText("Kind"), "cookies");
    expect(screen.getByLabelText("Secret").tagName).toBe("TEXTAREA");
    await userEvent.selectOptions(screen.getByLabelText("Kind"), "apprise");
    expect(screen.getByText("Apprise URL (e.g. ntfys://topic)")).toBeInTheDocument();
  });

  it("shows server message for rejected apprise host", async () => {
    server.use(
      http.get("*/api/v1/credentials", () => HttpResponse.json({ items: [], next_cursor: null })),
      http.post("*/api/v1/credentials", () => HttpResponse.json({ detail: "Private host not allowed" }, { status: 422 })),
    );
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Add credential" }));
    await userEvent.type(screen.getByLabelText("Name"), "n");
    await userEvent.type(screen.getByLabelText("Site"), "s");
    await userEvent.selectOptions(screen.getByLabelText("Kind"), "apprise");
    await userEvent.type(screen.getByLabelText("Secret"), "json://10.0.0.1");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Private host not allowed")).toBeInTheDocument();
  });
});
