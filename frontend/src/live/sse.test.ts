import { QueryClient, type InfiniteData } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setUnauthorizedHandler } from "../api/client";
import { keys } from "../api/keys";
import { server } from "../test/server";
import { FakeEventSource } from "../test/setup";
import { openStream } from "./sse";
import { useDashboardStream } from "./useDashboardStream";
import { MAX_LOG, useJobStream } from "./useJobStream";

const job = (id: number, extra = {}) => ({
  id, status: "running", counters: { a: 1 }, phase: null, source_id: 1, ...extra,
});
const listData = (...ids: number[]): InfiniteData<{ items: unknown[] }> => ({
  pages: [{ items: ids.map((i) => job(i)) }],
  pageParams: [null],
});

let qc: QueryClient;
const wrapper = ({ children }: { children: ReactNode }) =>
  createElement(QueryClientProvider, { client: qc }, children);
const es = (): FakeEventSource => {
  const s = FakeEventSource.instances.at(-1);
  if (!s) throw new Error("no EventSource");
  return s;
};
const tick = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});
afterEach(() => {
  vi.useRealTimers();
  setUnauthorizedHandler(() => {});
});

describe("dashboard stream", () => {
  it("progress updates job detail cache", () => {
    qc.setQueryData(keys.detail("jobs", 5), job(5));
    renderHook(() => useDashboardStream(), { wrapper });
    act(() => es().emit("progress", { type: "progress", job_id: 5, counters: { b: 2 } }));
    expect(qc.getQueryData<{ counters: object }>(keys.detail("jobs", 5))?.counters).toEqual({ a: 1, b: 2 });
  });

  it("phase and status patch infinite list pages", () => {
    qc.setQueryData(keys.list("jobs", { x: 1 }), listData(5, 6));
    renderHook(() => useDashboardStream(), { wrapper });
    act(() => {
      es().emit("phase", { job_id: 5, name: "download" });
      es().emit("status", { job_id: 6, status: "running" });
    });
    const d = qc.getQueryData<InfiniteData<{ items: { id: number; phase: string | null }[] }>>(
      keys.list("jobs", { x: 1 }),
    );
    expect(d?.pages[0]?.items[0]?.phase).toBe("download");
    expect(d?.pages[0]?.items[1]?.phase).toBeNull();
  });

  it("terminal status invalidates jobs and uploads", () => {
    qc.setQueryData(keys.list("jobs"), listData(1));
    const spy = vi.spyOn(qc, "invalidateQueries");
    renderHook(() => useDashboardStream(), { wrapper });
    act(() => es().emit("status", { job_id: 99, status: "succeeded" }));
    const ks = spy.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey[0]);
    expect(ks).toContain("list");
    expect(ks).toContain("uploads");
  });

  it("gap invalidates", () => {
    const spy = vi.spyOn(qc, "invalidateQueries");
    renderHook(() => useDashboardStream(), { wrapper });
    act(() => es().emit("gap", {}));
    expect(spy).toHaveBeenCalledWith({ queryKey: ["list", "jobs"] });
  });
});

describe("job stream", () => {
  it("dedupes replay by id", async () => {
    const { result } = renderHook(() => useJobStream(3), { wrapper });
    const l = { job_id: 3, ts: "t", level: "info", msg: "m" };
    act(() => {
      es().emit("log", { ...l, id: 1 });
      es().emit("item.uploaded", { id: 1, url: "u" });
    });
    await tick(100);
    act(() => {
      es().emit("log", { ...l, id: 1 });
      es().emit("log", { ...l, id: 2 });
      es().emit("item.uploaded", { id: 1, url: "u" });
    });
    await tick(100);
    expect(result.current.log.map((x) => x.id)).toEqual([1, 2]);
    expect(result.current.items).toHaveLength(1);
  });

  it("caps log buffer at 20000 and sets truncated", async () => {
    const { result } = renderHook(() => useJobStream(3), { wrapper });
    act(() => {
      for (let i = 1; i <= MAX_LOG + 50; i++) es().emit("log", { id: i, job_id: 3, ts: "t", level: "info", msg: "m" });
    });
    await tick(100);
    expect(result.current.log).toHaveLength(MAX_LOG);
    expect(result.current.log[0]?.id).toBe(51);
    expect(result.current.truncated).toBe(true);
  });

  it("batches a burst into one render and writes detail cache", async () => {
    qc.setQueryData(keys.detail("jobs", 3), job(3));
    let renders = 0;
    renderHook(() => { renders++; return useJobStream(3); }, { wrapper });
    const base = renders;
    act(() => {
      for (let i = 1; i <= 1000; i++) es().emit("log", { id: i, job_id: 3, ts: "t", level: "info", msg: "m" });
      es().emit("status", { job_id: 3, status: "failed" });
      es().emit("progress", { counters: { z: 9 } });
    });
    await tick(100);
    expect(renders - base).toBeLessThanOrEqual(10);
    const d = qc.getQueryData<{ status: string; counters: object }>(keys.detail("jobs", 3));
    expect(d?.status).toBe("failed");
    expect(d?.counters).toEqual({ a: 1, z: 9 });
  });

  it("closes on unmount", () => {
    const { unmount } = renderHook(() => useJobStream(3), { wrapper });
    const s = es();
    unmount();
    expect(s.readyState).toBe(2);
  });
});

describe("openStream", () => {
  it("reconnects with backoff", async () => {
    server.use(http.get("*/api/v1/auth/me", () => HttpResponse.json({ id: 1 })));
    const stop = openStream("/x", () => {});
    const seq = [1000, 2000, 5000, 10000, 10000];
    for (const [i, d] of seq.entries()) {
      es().fail();
      expect(FakeEventSource.instances).toHaveLength(i + 1);
      await tick(d - 1);
      expect(FakeEventSource.instances).toHaveLength(i + 1);
      await tick(1);
      expect(FakeEventSource.instances).toHaveLength(i + 2);
    }
    stop();
  });

  it("stops reconnecting after 401 probe", async () => {
    server.use(http.get("*/api/v1/auth/me", () => new HttpResponse(null, { status: 401 })));
    const unauth = vi.fn();
    setUnauthorizedHandler(unauth);
    openStream("/x", () => {});
    es().fail();
    await tick(1000);
    await tick(20000);
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(unauth).toHaveBeenCalledTimes(1);
  });

  it("end closes without reconnect", async () => {
    const onEnd = vi.fn();
    openStream("/x", () => {}, { onEnd });
    const s = es();
    s.emit("end", {});
    expect(s.readyState).toBe(2);
    s.fail();
    await tick(20000);
    expect(onEnd).toHaveBeenCalled();
    expect(FakeEventSource.instances).toHaveLength(1);
  });
});
