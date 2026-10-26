import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { toast } from "sonner";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { MeOut } from "../../api/me";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
const admin: MeOut = { id: 1, name: "Boss", email: "b@x.io", groups: ["ih-admin"], role: "admin" };
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
    await userEvent.clear(days);
    await userEvent.type(days, "45");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
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
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("too long")).toBeInTheDocument();
    expect(screen.getByLabelText("Retention (days)")).toHaveAttribute("aria-invalid", "true");
  });

  it("rate limit duplicate category blocked", async () => {
    server.use(doc({ rip: { rate_limits: { reddit: { sleep_request: 2, sleep: 0, retries: 4 } } } }));
    open("rip");
    const name = await screen.findByLabelText("New category");
    await userEvent.type(name, "reddit");
    await userEvent.click(screen.getByRole("button", { name: "Add category" }));
    expect(await screen.findByText("Category already exists")).toBeInTheDocument();
    expect(screen.getAllByLabelText(/Retries/)).toHaveLength(1);
    await userEvent.clear(name);
    await userEvent.type(name, "twitter");
    await userEvent.click(screen.getByRole("button", { name: "Add category" }));
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
    await userEvent.click(screen.getByRole("button", { name: "Show value" }));
    expect(input).toHaveAttribute("type", "text");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
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
    await userEvent.click(screen.getByRole("button", { name: "Back up now" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Backups are not supported for this database"));
  });

  it("prune confirms then toasts counts", async () => {
    server.use(
      http.get("*/api/v1/admin/backups", () => HttpResponse.json({ items: [] })),
      http.post("*/api/v1/admin/maintenance/prune", () => HttpResponse.json({ jobs: 3, ephemeral_sources: 1 })),
    );
    open("admin");
    await userEvent.click(await screen.findByRole("button", { name: "Prune now" }));
    await userEvent.click(screen.getByRole("button", { name: "Prune" }));
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
    await userEvent.upload(await screen.findByLabelText("Config file"), file);
    expect(await screen.findByText("bad row")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply import" })).toBeDisabled();
    expect(calls[0]).toMatchObject({ dry: "true", body: "sources: []\n" });
    expect(calls[0]!.type).toContain("application/yaml");

    errors = [];
    await userEvent.upload(screen.getByLabelText("Config file"), new File(["sources: []\n"], "c2.yaml"));
    await waitFor(() => expect(screen.queryByText("bad row")).not.toBeInTheDocument());
    const apply = screen.getByRole("button", { name: "Apply import" });
    await waitFor(() => expect(apply).toBeEnabled());
    await userEvent.click(apply);
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
    await userEvent.click(await screen.findByRole("radio", { name: /Encrypted/ }));
    await userEvent.click(screen.getByRole("button", { name: "Download" }));
    await waitFor(() => expect(name).toBe("immich-hoarder-config.yaml"));
    expect(q).toBe("encrypted");
    expect(await blob!.text()).toBe("sources: []\n");
  });
});
