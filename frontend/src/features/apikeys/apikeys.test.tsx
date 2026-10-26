import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { MeOut } from "../../api/me";
import { dashboardDefaults } from "../../test/handlers";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { SCOPES } from "./scopes";

const me: MeOut = { id: 1, name: "Own", email: "o@x.io", groups: [], role: "user" };
const k1 = { id: 1, name: "ci", prefix: "abcd1234", scopes: ["jobs:read"], expires_at: "2020-01-01T00:00:00Z" };
const PLAIN = "ih_abcd1234_SECRETSECRETSECRETSECRET12345678";
beforeAll(() => import("./ApiKeysPage"), 30_000);
const list = (items: object[]) => http.get("*/api/v1/api-keys", () => HttpResponse.json({ items, next_cursor: null }));

describe("api keys", () => {
  it("has the 13 scopes in order", () => expect(SCOPES).toHaveLength(13));

  it("reveal dialog ignores Escape and outside click", async () => {
    server.use(
      list([]),
      http.post("*/api/v1/api-keys", () =>
        HttpResponse.json({ id: 2, name: "n", prefix: "abcd1234", scopes: ["jobs:read"], expires_at: null, key: PLAIN }, { status: 201 }),
      ),
    );
    renderWithProviders(null, { me, route: "/api-keys" });
    await userEvent.click(await screen.findByRole("button", { name: "New API key" }));
    await userEvent.type(screen.getByLabelText("Name"), "n");
    await userEvent.click(screen.getByLabelText("jobs:read"));
    await userEvent.click(screen.getByRole("button", { name: "Create key" }));
    await screen.findByText("This key will not be shown again");
    await userEvent.keyboard("{Escape}");
    fireEvent.pointerDown(document.body);
    expect(screen.getByLabelText("API key")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(screen.queryByLabelText("API key")).not.toBeInTheDocument());
  });

  it("rejects a past expiry and sets min to today", async () => {
    server.use(list([]));
    renderWithProviders(null, { me, route: "/api-keys" });
    await userEvent.click(await screen.findByRole("button", { name: "New API key" }));
    const d = screen.getByLabelText("Expires (optional, UTC)");
    expect(d).toHaveAttribute("min", new Date().toISOString().slice(0, 10));
    await userEvent.type(screen.getByLabelText("Name"), "n");
    await userEvent.click(screen.getByLabelText("jobs:read"));
    fireEvent.change(d, { target: { value: "2020-01-01" } });
    await userEvent.click(screen.getByRole("button", { name: "Create key" }));
    expect(await screen.findByText("Expiry must be today or later")).toBeInTheDocument();
  });

  it("shows a backend 403 via the root error", async () => {
    server.use(list([]), http.post("*/api/v1/api-keys", () => HttpResponse.json({ detail: "cannot grant scopes beyond the calling key" }, { status: 403 })));
    renderWithProviders(null, { me, route: "/api-keys" });
    await userEvent.click(await screen.findByRole("button", { name: "New API key" }));
    await userEvent.type(screen.getByLabelText("Name"), "n");
    await userEvent.click(screen.getByLabelText("jobs:read"));
    await userEvent.click(screen.getByRole("button", { name: "Create key" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("cannot grant scopes beyond the calling key");
  });

  it("created key shown once and not cached", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    let body: unknown;
    server.use(
      list([]),
      http.post("*/api/v1/api-keys", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ id: 2, name: "n", prefix: "abcd1234", scopes: ["jobs:read"], expires_at: null, key: PLAIN }, { status: 201 });
      }),
    );
    const { queryClient } = renderWithProviders(null, { me, route: "/api-keys" });
    await userEvent.click(await screen.findByRole("button", { name: "New API key" }));
    await userEvent.type(screen.getByLabelText("Name"), "n");
    await userEvent.click(screen.getByLabelText("jobs:read"));
    fireEvent.change(screen.getByLabelText("Expires (optional, UTC)"), { target: { value: "2030-05-06" } });
    await userEvent.click(screen.getByRole("button", { name: "Create key" }));
    expect(await screen.findByText("This key will not be shown again")).toBeInTheDocument();
    expect(body).toEqual({ name: "n", scopes: ["jobs:read"], expires_at: "2030-05-06T23:59:59Z" });
    expect(screen.getByLabelText("API key")).toHaveValue(PLAIN);
    await userEvent.click(screen.getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledWith(PLAIN);
    const dump = () => JSON.stringify([queryClient.getQueryCache().getAll().map((q) => q.state.data), queryClient.getMutationCache().getAll().map((m) => m.state.data)]);
    expect(dump()).not.toContain("SECRETSECRET");
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(screen.queryByLabelText("API key")).not.toBeInTheDocument());
    expect(document.body.innerHTML).not.toContain("SECRETSECRET");
  });

  it("revoke confirms and removes", async () => {
    let revoked = false;
    server.use(
      http.get("*/api/v1/api-keys", () => HttpResponse.json({ items: revoked ? [] : [k1], next_cursor: null })),
      http.delete("*/api/v1/api-keys/1", () => {
        revoked = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderWithProviders(null, { me, route: "/api-keys" });
    expect(await screen.findByText("ci")).toBeInTheDocument();
    expect(screen.getByText("abcd1234…")).toBeInTheDocument();
    expect(screen.getByText(/Expired/)).toHaveClass("text-destructive");
    await userEvent.click(screen.getByRole("button", { name: "Revoke ci" }));
    await userEvent.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(screen.queryByText("ci")).not.toBeInTheDocument());
  });

  it("scope presets", async () => {
    server.use(list([]));
    renderWithProviders(null, { me, route: "/api-keys" });
    await userEvent.click(await screen.findByRole("button", { name: "New API key" }));
    expect(screen.queryByRole("checkbox", { name: "admin" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Read-only" }));
    const checked = () => screen.getAllByRole("checkbox").filter((c) => (c as HTMLInputElement).checked).map((c) => (c as HTMLInputElement).value);
    expect(checked()).toEqual(["sources:read", "targets:read", "credentials:read", "jobs:read", "keys:read", "metrics:read"]);
    await userEvent.click(screen.getByRole("button", { name: "All" }));
    expect(checked()).toHaveLength(12);
  });

  it("admin sees admin scope", async () => {
    server.use(list([]), ...dashboardDefaults);
    renderWithProviders(null, { me: { ...me, role: "admin" }, route: "/api-keys" });
    await userEvent.click(await screen.findByRole("button", { name: "New API key" }));
    expect(screen.getByRole("checkbox", { name: "admin" })).toBeInTheDocument();
  });
});
