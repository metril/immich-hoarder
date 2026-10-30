import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { toast } from "sonner";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { MeOut } from "../../api/me";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";

const user = userEvent.setup({ delay: null });

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
const admin: MeOut = { id: 1, name: "Boss", email: "b@x.io", groups: ["ih-admin"], role: "admin", must_change_password: false };
beforeAll(() => import("./SettingsPage"), 30_000);
const open = (tab: string) => renderWithProviders(null, { me: admin, route: `/settings?tab=${tab}` });
const doc = (d: object = {}) => http.get("*/api/v1/settings", () => HttpResponse.json(d));

describe("settings", () => {
  it("runtime form puts only runtime key", async () => {
    let body: Record<string, unknown> | undefined;
    server.use(
      doc({ rip: { upload_concurrency: 2 } }),
      http.put("*/api/v1/settings", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(body);
      }),
    );
    open("runtime");
    const days = await screen.findByLabelText("Retention (days)");
    expect(days).toHaveValue(30);
    await user.clear(days);
    await user.type(days, "45");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(body).toBeDefined());
    expect(Object.keys(body!)).toEqual(["runtime"]);
    expect(body!.runtime).toMatchObject({ retention_days: 45, backup_cron: "0 3 * * *", backup_keep: 7, cancel_grace_s: 10, max_concurrent_jobs: null });
  });

  it("422 from server maps to retention field", async () => {
    server.use(
      doc(),
      http.put("*/api/v1/settings", () =>
        HttpResponse.json({ detail: [{ loc: ["body", "runtime", "retention_days"], msg: "too long", type: "x" }] }, { status: 422 }),
      ),
    );
    open("runtime");
    await screen.findByLabelText("Retention (days)");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("too long")).toBeInTheDocument();
    expect(screen.getByLabelText("Retention (days)")).toHaveAttribute("aria-invalid", "true");
  });

  it("rate limit duplicate category blocked", async () => {
    server.use(doc({ rip: { rate_limits: { reddit: { sleep_request: 2, sleep: 0, retries: 4 } } } }));
    open("rip");
    const name = await screen.findByLabelText("New category");
    await user.type(name, "reddit");
    await user.click(screen.getByRole("button", { name: "Add category" }));
    expect(await screen.findByText("Category already exists")).toBeInTheDocument();
    expect(screen.getAllByLabelText(/Retries/)).toHaveLength(1);
    await user.clear(name);
    await user.type(name, "twitter");
    await user.click(screen.getByRole("button", { name: "Add category" }));
    expect(screen.getAllByLabelText(/Retries/)).toHaveLength(2);
  });

  it("notify urls masked by default", async () => {
    let body: Record<string, unknown> | undefined;
    server.use(
      doc({ notify: { on: ["failure"], urls: ["discord://secret/token"] } }),
      http.put("*/api/v1/settings", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(body);
      }),
    );
    open("notify");
    const input = await screen.findByLabelText("Notification URL 1");
    expect(input).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: "Show value" }));
    expect(input).toHaveAttribute("type", "text");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(body).toBeDefined());
    expect(body).toEqual({ notify: { on: ["failure"], urls: ["discord://secret/token"] } });
    expect(JSON.stringify(vi.mocked(toast.success).mock.calls)).not.toContain("secret");
  });

  it("backup 409 shows unsupported message", async () => {
    server.use(
      http.get("*/api/v1/admin/backups", () => HttpResponse.json({ items: [{ file: "a.dump", mtime: "2026-10-01T00:00:00Z", size: 2048 }] })),
      http.post("*/api/v1/admin/backup", () => HttpResponse.json({ detail: "postgres" }, { status: 409 })),
    );
    open("admin");
    expect(await screen.findByText("a.dump")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back up now" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Backups are not supported for this database"));
  });

  it("restore needs typed confirmation and shows restart-required state", async () => {
    let pending = false;
    let q = "";
    server.use(
      http.get("*/api/v1/admin/backups", () =>
        HttpResponse.json({ items: [{ file: "a.db", mtime: "2026-10-01T00:00:00Z", size: 2048 }], restore_pending: pending }),
      ),
      http.post("*/api/v1/admin/backups/a.db/restore", ({ request }) => {
        q = new URL(request.url).search;
        pending = true;
        return HttpResponse.json({ restart_required: true, restarting: false }, { status: 202 });
      }),
      http.delete("*/api/v1/admin/backups/pending-restore", () => {
        pending = false;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    open("admin");
    await user.click(await screen.findByRole("button", { name: "Restore a.db" }));
    const go = screen.getByRole("button", { name: "Restore" });
    expect(go).toBeDisabled();
    await user.type(screen.getByLabelText(/Type RESTORE/), "restore");
    expect(go).toBeDisabled();
    await user.clear(screen.getByLabelText(/Type RESTORE/));
    await user.type(screen.getByLabelText(/Type RESTORE/), "RESTORE");
    await user.click(go);
    await waitFor(() => expect(q).toContain("restart=false"));
    expect(await screen.findByText(/A restore is staged/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel restore" }));
    await waitFor(() => expect(screen.queryByText(/A restore is staged/)).not.toBeInTheDocument());
  });

  it("deletes a backup after confirmation", async () => {
    let deleted = false;
    server.use(
      http.get("*/api/v1/admin/backups", () =>
        HttpResponse.json({ items: deleted ? [] : [{ file: "a.db", mtime: "2026-10-01T00:00:00Z", size: 2048 }], restore_pending: false }),
      ),
      http.delete("*/api/v1/admin/backups/a.db", () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    open("admin");
    await user.click(await screen.findByRole("button", { name: "Delete a.db" }));
    await user.click(await screen.findByRole("button", { name: "Delete" }));
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("prune confirms then toasts counts", async () => {
    server.use(
      http.get("*/api/v1/admin/backups", () => HttpResponse.json({ items: [] })),
      http.post("*/api/v1/admin/maintenance/prune", () => HttpResponse.json({ jobs: 3, ephemeral_sources: 1 })),
    );
    open("admin");
    await user.click(await screen.findByRole("button", { name: "Prune now" }));
    await user.click(screen.getByRole("button", { name: "Prune" }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Pruned 3 jobs, 1 ephemeral sources"));
  });

  it("import dry-run then apply; apply disabled on errors", async () => {
    const calls: { dry: string | null; type: string | null; body: string }[] = [];
    let errors: string[] = ["bad row"];
    server.use(
      http.get("*/api/v1/admin/backups", () => HttpResponse.json({ items: [] })),
      http.post("*/api/v1/admin/import", async ({ request }) => {
        const dry = new URL(request.url).searchParams.get("dry_run");
        calls.push({ dry, type: request.headers.get("content-type"), body: await request.text() });
        return HttpResponse.json({ created: { sources: 1 }, skipped: {}, errors: dry === "true" ? errors : [], applied: dry === "false" });
      }),
    );
    open("admin");
    const file = new File(["sources: []\n"], "c.yaml", { type: "application/yaml" });
    await user.upload(await screen.findByLabelText("Config file"), file);
    expect(await screen.findByText("bad row")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply import" })).toBeDisabled();
    expect(calls[0]).toMatchObject({ dry: "true", body: "sources: []\n" });
    expect(calls[0]!.type).toContain("application/yaml");

    errors = [];
    await user.upload(screen.getByLabelText("Config file"), new File(["sources: []\n"], "c2.yaml"));
    await waitFor(() => expect(screen.queryByText("bad row")).not.toBeInTheDocument());
    const apply = screen.getByRole("button", { name: "Apply import" });
    await waitFor(() => expect(apply).toBeEnabled());
    await user.click(apply);
    await waitFor(() => expect(calls.at(-1)!.dry).toBe("false"));
    expect(calls.at(-1)!.body).toBe("sources: []\n");
  });

  it("import rejects >5MB client-side", async () => {
    server.use(http.get("*/api/v1/admin/backups", () => HttpResponse.json({ items: [] })));
    open("admin");
    const input = await screen.findByLabelText("Config file");
    const big = new File(["x"], "big.yaml");
    Object.defineProperty(big, "size", { value: 5 * 1024 * 1024 + 1 });
    fireEvent.change(input, { target: { files: [big] } });
    expect(await screen.findByText("File is larger than 5 MB")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Apply import" })).not.toBeInTheDocument();
  });

  it("export downloads yaml", async () => {
    let q: string | null = null;
    server.use(
      http.get("*/api/v1/admin/backups", () => HttpResponse.json({ items: [] })),
      http.get("*/api/v1/admin/export", ({ request }) => {
        q = new URL(request.url).searchParams.get("secrets");
        return new HttpResponse("sources: []\n", { headers: { "content-type": "application/yaml" } });
      }),
    );
    let blob: Blob | undefined;
    URL.createObjectURL = vi.fn((b: Blob | MediaSource) => ((blob = b as Blob), "blob:x"));
    URL.revokeObjectURL = vi.fn();
    let name = "";
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      name = this.download;
    });
    open("admin");
    await user.click(await screen.findByRole("radio", { name: /Encrypted/ }));
    await user.click(screen.getByRole("button", { name: "Download" }));
    await waitFor(() => expect(name).toBe("immich-hoarder-config.yaml"));
    expect(q).toBe("encrypted");
    expect(await blob!.text()).toBe("sources: []\n");
  });

  it("backup 507 shows disk error", async () => {
    server.use(
      http.get("*/api/v1/admin/backups", () => HttpResponse.json({ items: [] })),
      http.post("*/api/v1/admin/backup", () => HttpResponse.json({ detail: "disk" }, { status: 507 })),
    );
    open("admin");
    await user.click(await screen.findByRole("button", { name: "Back up now" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Backup failed: disk error or no space left"));
  });

  it("422 on notify urls list shows under the list", async () => {
    server.use(
      doc({ notify: { on: ["failure"], urls: ["discord://a/b"] } }),
      http.put("*/api/v1/settings", () =>
        HttpResponse.json({ detail: [{ loc: ["body", "notify", "urls"], msg: "too many urls", type: "x" }] }, { status: 422 }),
      ),
    );
    open("notify");
    await screen.findByLabelText("Notification URL 1");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("too many urls")).toBeInTheDocument();
  });

  it("rate limit field errors show per row", async () => {
    server.use(
      doc({ rip: { rate_limits: { reddit: { sleep_request: 2, sleep: 0, retries: 4 } } } }),
      http.put("*/api/v1/settings", () =>
        HttpResponse.json({ detail: [{ loc: ["body", "rip", "rate_limits", "reddit", "retries"], msg: "too high", type: "x" }] }, { status: 422 }),
      ),
    );
    open("rip");
    const retries = await screen.findByLabelText(/Retries/);
    await user.clear(retries);
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Required")).toBeInTheDocument();
    expect(retries).toHaveAttribute("aria-invalid", "true");
    await user.type(retries, "9");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("too high")).toBeInTheDocument();
  });

  it("tabs move with arrow keys", async () => {
    server.use(doc());
    const { router } = open("rip");
    const tab = await screen.findByRole("tab", { name: "Rip" });
    tab.focus();
    await user.keyboard("{ArrowRight}");
    await waitFor(() => expect(router.state.location.search).toMatchObject({ tab: "runtime" }));
    expect(screen.getByRole("tab", { name: "Rip" })).toHaveAttribute("tabindex", "-1");
  });

  it("auth form: blank secret sent as null, shows set state, test button reports", async () => {
    let body: Record<string, unknown> | undefined;
    server.use(
      doc({ oidc: { enabled: true, issuer: "https://i.x", client_id: "cid", client_secret_set: true, admin_groups: ["a"], user_groups: ["u"], groups_claim: "groups" }, auth: { public_url: null, local_enabled: true } }),
      http.post("*/api/v1/settings/oidc/test", () => HttpResponse.json({ ok: false, error: "unreachable" })),
      http.put("*/api/v1/settings", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(body);
      }),
    );
    open("auth");
    expect(await screen.findByDisplayValue("https://i.x")).toBeInTheDocument();
    expect(screen.getByText("A secret is set. Leave blank to keep it.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Test issuer" }));
    expect(await screen.findByText("unreachable")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(body).toBeDefined());
    expect(body!.oidc as object).toMatchObject({ enabled: true, client_secret: null, admin_groups: ["a"], user_groups: ["u"] });
    expect(body!.auth).toEqual({ public_url: null, local_enabled: true });
  });

  it("auth form surfaces 422 message", async () => {
    server.use(doc(), http.put("*/api/v1/settings", () => HttpResponse.json({ detail: "Cannot disable local login without working OIDC" }, { status: 422 })));
    open("auth");
    await screen.findByLabelText("Issuer URL");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Cannot disable local login without working OIDC")).toBeInTheDocument();
  });

  it("change password sends current and new", async () => {
    let body: unknown;
    server.use(doc(), http.put("*/api/v1/settings/local-admin", async ({ request }) => {
      body = await request.json();
      return new HttpResponse(null, { status: 204 });
    }));
    open("auth");
    await user.type(await screen.findByLabelText("Current password"), "oldpass12");
    await user.type(screen.getByLabelText("New password"), "newpass123");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    await waitFor(() => expect(body).toEqual({ current_password: "oldpass12", new_password: "newpass123" }));
  });
});
