import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MeOut } from "../../api/me";
import { server } from "../../test/server";
import { renderWithProviders } from "../../test/render";
import { pageReload } from "./reload";
import { RouteError } from "./RouteError";
import { useShortcuts } from "./shortcuts";
import { resetThemeCache, useTheme } from "./theme";

const admin: MeOut = { id: 1, name: "Ada", email: "a@x.io", groups: [], role: "admin" };
const user: MeOut = { ...admin, id: 2, name: "Bob", role: "user" };

beforeEach(() => {
  server.use(http.head("*/api/v1/auth/login", () => new HttpResponse(null, { status: 204 })));
});
afterEach(() => {
  localStorage.clear();
  resetThemeCache();
  sessionStorage.clear();
  document.documentElement.classList.remove("dark");
  vi.restoreAllMocks();
});

const nav = () => screen.getByRole("navigation", { name: "Main" });

describe("auth gate", () => {
  it("redirects to login when me is null", async () => {
    const { router } = renderWithProviders(null, { me: null, route: "/" });
    expect(await screen.findByRole("link", { name: "Sign in with SSO" })).toHaveAttribute("href", "/api/v1/auth/login");
    expect(router.state.location.pathname).toBe("/login");
  });

  it("shows OIDC hint only on 503", async () => {
    server.use(http.head("*/api/v1/auth/login", () => new HttpResponse(null, { status: 503 })));
    renderWithProviders(null, { me: null, route: "/login" });
    expect(await screen.findByText(/OIDC is not configured/)).toBeInTheDocument();
  });

  it("non-admin visiting /settings redirects home", async () => {
    const { router } = renderWithProviders(null, { me: user, route: "/settings" });
    await screen.findByRole("navigation", { name: "Main" });
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
  });
});

describe("nav", () => {
  it("user nav hides Users and Settings", async () => {
    renderWithProviders(null, { me: user, route: "/" });
    await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav()).getAllByRole("link")).toHaveLength(6);
    expect(within(nav()).queryByRole("link", { name: "Users" })).toBeNull();
    expect(within(nav()).queryByRole("link", { name: "Settings" })).toBeNull();
  });

  it("admin nav shows all 8", async () => {
    renderWithProviders(null, { me: admin, route: "/" });
    await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav()).getAllByRole("link")).toHaveLength(8);
  });

  it("mobile: hamburger opens sheet nav", async () => {
    window.innerWidth = 375;
    const u = userEvent.setup();
    renderWithProviders(null, { me: admin, route: "/" });
    await u.click(await screen.findByRole("button", { name: "Open navigation" }));
    const sheet = await screen.findByRole("dialog", { name: "Navigation" });
    await u.click(within(sheet).getByRole("link", { name: "Jobs" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Navigation" })).toBeNull());
  });
});

describe("theme", () => {
  it("theme toggle persists and sets dark class", async () => {
    const u = userEvent.setup();
    renderWithProviders(null, { me: admin, route: "/" });
    await u.click(await screen.findByRole("button", { name: "Theme" }));
    await u.click(screen.getByRole("menuitemradio", { name: "Dark" }));
    expect(localStorage.getItem("ih-theme")).toBe("dark");
    expect(document.documentElement).toHaveClass("dark");
    await u.click(screen.getByRole("button", { name: "Theme" }));
    await u.click(screen.getByRole("menuitemradio", { name: "Light" }));
    expect(document.documentElement).not.toHaveClass("dark");
  });

  it("system theme follows matchMedia", () => {
    let matches = false;
    const listeners = new Set<() => void>();
    vi.spyOn(window, "matchMedia").mockImplementation(
      (q) =>
        ({
          media: q,
          get matches() {
            return matches;
          },
          addEventListener: (_: string, fn: () => void) => listeners.add(fn),
          removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
        }) as unknown as MediaQueryList,
    );
    function H() {
      useTheme();
      return null;
    }
    render(<H />);
    expect(document.documentElement).not.toHaveClass("dark");
    matches = true;
    act(() => listeners.forEach((f) => f()));
    expect(document.documentElement).toHaveClass("dark");
  });
});

describe("shortcuts", () => {
  it("mod+k opens palette and navigates", async () => {
    const u = userEvent.setup();
    const { router } = renderWithProviders(null, { me: admin, route: "/" });
    await screen.findByRole("navigation", { name: "Main" });
    await u.keyboard("{Control>}k{/Control}");
    const dlg = await screen.findByRole("dialog");
    await u.type(within(dlg).getByRole("combobox"), "Targets");
    await u.keyboard("{Enter}");
    await waitFor(() => expect(router.state.location.pathname).toBe("/targets"));
  });

  it("g j navigates to jobs", async () => {
    const u = userEvent.setup();
    const { router } = renderWithProviders(null, { me: admin, route: "/" });
    await screen.findByRole("navigation", { name: "Main" });
    await u.keyboard("gj");
    await waitFor(() => expect(router.state.location.pathname).toBe("/jobs"));
  });

  it("shortcuts ignored in inputs", async () => {
    const u = userEvent.setup();
    const fn = vi.fn();
    function H() {
      useShortcuts({ "g j": fn, "?": fn });
      return <input aria-label="q" />;
    }
    renderWithProviders(<H />);
    await u.click(await screen.findByLabelText("q"));
    await u.keyboard("gj?");
    expect(fn).not.toHaveBeenCalled();
    await u.click(document.body);
    await u.keyboard("gj");
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("? opens help", async () => {
    const u = userEvent.setup();
    renderWithProviders(null, { me: admin, route: "/" });
    await screen.findByRole("navigation", { name: "Main" });
    await u.keyboard("?");
    expect(await screen.findByRole("dialog", { name: "Keyboard shortcuts" })).toBeInTheDocument();
  });
});

describe("RouteError", () => {
  it("reloads once on chunk load error", () => {
    const reload = vi.spyOn(pageReload, "reload").mockImplementation(() => {});
    const err = new TypeError("Failed to fetch dynamically imported module: /assets/x.js");
    const { unmount } = render(<RouteError error={err} reset={() => {}} />);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem("ih-reloaded")).toBe("1");
    unmount();
    render(<RouteError error={err} reset={() => {}} />);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows message and retries for other errors", () => {
    const reset = vi.fn();
    render(<RouteError error={new Error("boom")} reset={reset} />);
    expect(screen.getByText("boom")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(reset).toHaveBeenCalled();
  });
});
