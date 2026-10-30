import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { toast } from "sonner";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { MeOut } from "../../api/me";
import { dashboardDefaults } from "../../test/handlers";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";

const user = userEvent.setup({ delay: null });

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
const admin: MeOut = { id: 1, name: "Boss", email: "b@x.io", groups: ["ih-admin"], role: "admin", must_change_password: false };
const u = (id: number, name: string, role = "user", disabled = false) => ({ id, sub: `s${id}`, name, email: `${name}@x.io`, groups: ["g"], role, disabled });
beforeAll(() => import("./UsersPage"), 30_000);

describe("users", () => {
  it("users route redirects non-admin", async () => {
    server.use(...dashboardDefaults);
    const { router } = renderWithProviders(null, { me: { ...admin, role: "user" }, route: "/users" });
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
  });

  it("disable switch reverts on last-admin error", async () => {
    server.use(
      http.get("*/api/v1/users", () => HttpResponse.json({ items: [u(1, "Boss", "admin"), u(2, "Other", "admin")], next_cursor: null })),
      http.patch("*/api/v1/users/2", () => HttpResponse.json({ detail: "last admin" }, { status: 409 })),
    );
    renderWithProviders(null, { me: admin, route: "/users" });
    const sw = await screen.findByRole("switch", { name: "Disabled: Other" });
    expect(screen.getByRole("switch", { name: "Disabled: Boss" })).toBeDisabled();
    await user.click(sw);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Cannot disable the last admin"));
    await waitFor(() => expect(sw).toHaveAttribute("aria-checked", "false"));
  });

  it("409 with another detail shows the server message", async () => {
    server.use(
      http.get("*/api/v1/users", () => HttpResponse.json({ items: [u(1, "Boss", "admin"), u(2, "Other")], next_cursor: null })),
      http.patch("*/api/v1/users/2", () => HttpResponse.json({ detail: "conflict elsewhere" }, { status: 409 })),
    );
    renderWithProviders(null, { me: admin, route: "/users" });
    await user.click(await screen.findByRole("switch", { name: "Disabled: Other" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("conflict elsewhere"));
  });

  it("disables a user", async () => {
    let body: unknown;
    server.use(
      http.get("*/api/v1/users", () => HttpResponse.json({ items: [u(1, "Boss", "admin"), u(2, "Other")], next_cursor: null })),
      http.patch("*/api/v1/users/2", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(u(2, "Other", "user", true));
      }),
    );
    renderWithProviders(null, { me: admin, route: "/users" });
    await user.click(await screen.findByRole("switch", { name: "Disabled: Other" }));
    await waitFor(() => expect(body).toEqual({ disabled: true }));
  });

  it("creates a local user", async () => {
    let body: unknown;
    server.use(
      http.get("*/api/v1/users", () => HttpResponse.json({ items: [u(1, "Boss", "admin")], next_cursor: null })),
      http.post("*/api/v1/users/local", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(u(3, "carol"), { status: 201 });
      }),
    );
    renderWithProviders(null, { me: admin, route: "/users" });
    await user.click(await screen.findByRole("button", { name: "New local user" }));
    await user.type(screen.getByLabelText("Username"), "carol");
    await user.type(screen.getByLabelText("Password"), "password-1234");
    await user.click(screen.getByRole("button", { name: "Create user" }));
    await waitFor(() => expect(body).toMatchObject({ username: "carol", password: "password-1234", role: "user" }));
  });

  it("resets a local user's password", async () => {
    let body: unknown;
    server.use(
      http.get("*/api/v1/users", () => HttpResponse.json({ items: [u(1, "Boss", "admin"), { ...u(2, "Other"), sub: "local:other" }], next_cursor: null })),
      http.post("*/api/v1/users/2/password", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(u(2, "Other"));
      }),
    );
    renderWithProviders(null, { me: admin, route: "/users" });
    await user.click(await screen.findByRole("button", { name: "Reset password: Other" }));
    await user.type(screen.getByLabelText("New password"), "brand-new-pass");
    await user.click(screen.getByRole("button", { name: "Reset password" }));
    await waitFor(() => expect(body).toEqual({ new_password: "brand-new-pass", must_change_password: true }));
  });

  it("delete asks for a reassignment target when the user owns resources", async () => {
    const urls: string[] = [];
    server.use(
      http.get("*/api/v1/users", () =>
        HttpResponse.json({ items: [u(1, "Boss", "admin"), { ...u(2, "Other"), sub: "local:other" }], next_cursor: null }),
      ),
      http.delete("*/api/v1/users/2", ({ request }) => {
        urls.push(request.url);
        return new URL(request.url).searchParams.has("reassign_to")
          ? new HttpResponse(null, { status: 204 })
          : HttpResponse.json({ detail: "user owns resources", owned: { targets: 1, credentials: 0, sources: 2 } }, { status: 409 });
      }),
    );
    renderWithProviders(null, { me: admin, route: "/users" });
    await user.click(await screen.findByRole("button", { name: "Delete: Other" }));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    await screen.findByText(/owns 1 target\(s\)/);
    await user.selectOptions(screen.getByLabelText("Reassign to"), "1");
    await user.click(screen.getByRole("button", { name: "Reassign and delete" }));
    await waitFor(() => expect(urls.at(-1)).toContain("reassign_to=1"));
  });
});
