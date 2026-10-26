import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { FakeEventSource } from "../../test/setup";
import { LogViewer } from "./LogViewer";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const ev = (id: number, level = "info", msg = `line ${id}`) => ({ id, ts: "2026-10-26T10:00:00Z", level, type: "log", data: { msg } });
const logMsg = (id: number, level = "info", msg = `line ${id}`) => ({ type: "log", id, ts: "2026-10-26T10:00:00Z", job_id: 1, level, msg });
const api = (items: unknown[]) => server.use(http.get("*/api/v1/jobs/1/events", () => HttpResponse.json({ items, next_cursor: null })));
const stream = () => FakeEventSource.instances.at(-1)!;
const rows = () => screen.queryAllByTestId("log-row");

describe("LogViewer", () => {
  it("filters by min level", async () => {
    api([ev(2, "warn", "careful"), ev(1, "info", "hi")]);
    renderWithProviders(<LogViewer jobId={1} live />);
    await screen.findByText("careful");
    act(() => stream().emit("log", logMsg(3, "debug", "noisy")));
    await screen.findByText("hi");
    expect(screen.queryByText("noisy")).toBeNull();
    await userEvent.selectOptions(screen.getByLabelText("Level"), "warn");
    await waitFor(() => expect(screen.queryByText("hi")).toBeNull());
    expect(screen.getByText("careful")).toBeInTheDocument();
  });

  it("search is case-insensitive and highlights", async () => {
    api([ev(1, "info", "Upload Done"), ev(2, "info", "other")]);
    renderWithProviders(<LogViewer jobId={1} live />);
    await screen.findByText("other");
    await userEvent.type(screen.getByLabelText("Search log"), "upLOAD");
    await waitFor(() => expect(screen.queryByText("other")).toBeNull());
    expect(screen.getByText("Upload", { selector: "mark" })).toBeInTheDocument();
  });

  it("auto-scroll disables on scroll up and re-enables via jump", async () => {
    api([ev(1)]);
    renderWithProviders(<LogViewer jobId={1} live />);
    await screen.findByText("line 1");
    const toggle = screen.getByRole("button", { name: "Auto-scroll" });
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    const el = screen.getByRole("log");
    Object.defineProperty(el, "scrollHeight", { configurable: true, value: 5000 });
    Object.defineProperty(el, "clientHeight", { configurable: true, value: 400 });
    el.scrollTop = 100;
    fireEvent.scroll(el);
    await waitFor(() => expect(toggle).toHaveAttribute("aria-pressed", "false"));
    await userEvent.click(screen.getByRole("button", { name: "Jump to latest" }));
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: "Jump to latest" })).toBeNull();
  });

  it("caps buffer at 20000", async () => {
    api([]);
    renderWithProviders(<LogViewer jobId={1} live />);
    await waitFor(() => expect(FakeEventSource.instances.length).toBeGreaterThan(0));
    act(() => {
      for (let i = 1; i <= 25_000; i++) stream().emit("log", logMsg(i));
    });
    await screen.findByText(/latest 20,000 lines/, undefined, { timeout: 5000 });
    expect(rows().length).toBeGreaterThan(0);
    expect(rows().length).toBeLessThan(100);
  }, 30_000);

  it("merges api page and stream without duplicates in id order", async () => {
    api([ev(3), ev(2), ev(1)]);
    renderWithProviders(<LogViewer jobId={1} live />);
    await screen.findByText("line 1");
    act(() => {
      stream().emit("log", logMsg(3));
      stream().emit("log", logMsg(4));
      stream().emit("log", logMsg(5));
    });
    await screen.findByText("line 5");
    expect(rows().map((r) => /line (\d+)/.exec(r.textContent ?? "")?.[1])).toEqual(["1", "2", "3", "4", "5"]);
  });
});
