import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse, delay } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { PreviewPanel } from "./PreviewPanel";
import type { SourceIn } from "./hooks";

const draft = { name: "x", url: "https://e.com/x", target_id: 1 } as SourceIn;

afterEach(() => vi.restoreAllMocks());

describe("PreviewPanel", () => {
  it("preview renders verdicts and aborts on close", async () => {
    let body: Record<string, unknown> = {};
    server.use(
      http.post("*/api/v1/sources/preview", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          items: [
            { url: "https://e.com/a.jpg", title: "Alpha", date: "2026-01-02", filename: "a.jpg", verdict: null },
            { url: "https://e.com/b.jpg", title: null, date: null, filename: "b.jpg", verdict: "too small" },
          ],
        });
      }),
    );
    const { unmount } = renderWithProviders(<PreviewPanel draft={draft} />);
    await userEvent.click(await screen.findByRole("button", { name: "Dry run" }));
    expect(await screen.findByText("would grab")).toBeInTheDocument();
    expect(screen.getByText("too small")).toBeInTheDocument();
    expect(body).toMatchObject({ url: "https://e.com/x", limit: 50 });

    // a slow run is aborted when the panel closes
    server.use(http.post("*/api/v1/sources/preview", async () => { await delay("infinite"); return HttpResponse.json({ items: [] }); }));
    const abort = vi.spyOn(AbortController.prototype, "abort");
    await userEvent.click(screen.getByRole("button", { name: "Dry run" }));
    expect(await screen.findByRole("status")).toBeInTheDocument();
    abort.mockClear();
    unmount();
    expect(abort).toHaveBeenCalled();
  });

  it("surfaces backend detail on busy", async () => {
    server.use(http.post("*/api/v1/sources/preview", () => HttpResponse.json({ detail: "preview capacity reached" }, { status: 429 })));
    renderWithProviders(<PreviewPanel draft={draft} />);
    await userEvent.click(await screen.findByRole("button", { name: "Dry run" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("preview capacity reached"));
    expect(screen.getByRole("alert")).toHaveTextContent("busy");
  });

  it("shows a timeout message when the client timeout fires", async () => {
    vi.spyOn(AbortSignal, "timeout").mockImplementation(() => AbortSignal.abort(new DOMException("t", "TimeoutError")));
    server.use(http.post("*/api/v1/sources/preview", async () => { await delay(50); return HttpResponse.json({ items: [] }); }));
    renderWithProviders(<PreviewPanel draft={draft} />);
    await userEvent.click(await screen.findByRole("button", { name: "Dry run" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Preview timed out"));
  });
});
