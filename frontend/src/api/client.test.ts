import { QueryClient } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { server } from "../test/server";
import { api, setUnauthorizedHandler } from "./client";
import { keys } from "./keys";
import { meQuery } from "./me";

afterEach(() => {
  document.cookie = "ih_csrf=; max-age=0";
  setUnauthorizedHandler(() => {});
});

describe("api client", () => {
  it("adds csrf header on mutations only", async () => {
    document.cookie = "ih_csrf=tok123";
    const seen: Record<string, string | null> = {};
    server.use(
      http.get("*/api/v1/targets", ({ request }) => {
        seen.get = request.headers.get("x-csrf-token");
        return HttpResponse.json({ items: [], next_cursor: null });
      }),
      http.delete("*/api/v1/targets/1", ({ request }) => {
        seen.del = request.headers.get("x-csrf-token");
        return new HttpResponse(null, { status: 204 });
      }),
    );
    await api.GET("/api/v1/targets", {});
    await api.DELETE("/api/v1/targets/{obj_id}", { params: { path: { obj_id: 1 } } });
    expect(seen.get).toBeNull();
    expect(seen.del).toBe("tok123");
  });

  it("401 calls unauthorized handler", async () => {
    const fn = vi.fn();
    setUnauthorizedHandler(fn);
    server.use(http.get("*/api/v1/targets", () => new HttpResponse(null, { status: 401 })));
    await api.GET("/api/v1/targets", {});
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("401 clears me", async () => {
    const qc = new QueryClient();
    qc.setQueryData(keys.me(), { id: 1, role: "admin", email: null, name: null, groups: [] });
    setUnauthorizedHandler(() => qc.setQueryData(keys.me(), null));
    server.use(http.get("*/api/v1/targets", () => new HttpResponse(null, { status: 401 })));
    await api.GET("/api/v1/targets", {});
    expect(qc.getQueryData(keys.me())).toBeNull();
  });

  it("meQuery resolves null on 401", async () => {
    server.use(http.get("*/api/v1/auth/me", () => new HttpResponse(null, { status: 401 })));
    const qc = new QueryClient();
    expect(await qc.fetchQuery(meQuery)).toBeNull();
  });
});
