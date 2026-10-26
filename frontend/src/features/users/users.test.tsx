import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { toast } from "sonner";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { MeOut } from "../../api/me";
import { dashboardDefaults } from "../../test/handlers";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
const admin: MeOut = { id: 1, name: "Boss", email: "b@x.io", groups: ["ih-admin"], role: "admin" };
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
    await userEvent.click(sw);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Cannot disable the last admin"));
    await waitFor(() => expect(sw).toHaveAttribute("aria-checked", "false"));
  });

  it("409 with another detail shows the server message", async () => {
    server.use(
      http.get("*/api/v1/users", () => HttpResponse.json({ items: [u(1, "Boss", "admin"), u(2, "Other")], next_cursor: null })),
      http.patch("*/api/v1/users/2", () => HttpResponse.json({ detail: "conflict elsewhere" }, { status: 409 })),
    );
    renderWithProviders(null, { me: admin, route: "/users" });
    await userEvent.click(await screen.findByRole("switch", { name: "Disabled: Other" }));
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
    await userEvent.click(await screen.findByRole("switch", { name: "Disabled: Other" }));
    await waitFor(() => expect(body).toEqual({ disabled: true }));
  });
});
