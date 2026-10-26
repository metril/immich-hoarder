import { describe, expect, it } from "vitest";
import { ApiError, unwrap } from "./errors";

const res = (status: number) => new Response(null, { status });

describe("unwrap", () => {
  it("returns data", () => {
    expect(unwrap({ data: { a: 1 }, response: res(200) })).toEqual({ a: 1 });
  });

  it("maps 422 detail to fieldErrors", () => {
    const detail = [
      { loc: ["body", "runtime", "retention_days"], msg: "too small", type: "x" },
      { loc: ["body", "cron"], msg: "bad cron", type: "x" },
    ];
    try {
      unwrap({ error: { detail }, response: res(422) });
      expect.unreachable();
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      const err = e as ApiError;
      expect(err.status).toBe(422);
      expect(err.fieldErrors).toEqual({ "runtime.retention_days": "too small", cron: "bad cron" });
    }
  });

  it("string detail becomes message", () => {
    try {
      unwrap({ error: { detail: "nope" }, response: res(403) });
      expect.unreachable();
    } catch (e) {
      expect((e as ApiError).message).toBe("nope");
      expect((e as ApiError).status).toBe(403);
    }
  });

  it("object detail keeps job_id and uses msg", () => {
    try {
      unwrap({ error: { detail: { msg: "already running", job_id: 7 } }, response: res(409) });
      expect.unreachable();
    } catch (e) {
      const err = e as ApiError;
      expect(err.message).toBe("already running");
      expect(err.detail).toEqual({ msg: "already running", job_id: 7 });
    }
  });

  it("falls back to status text", () => {
    try {
      unwrap({ error: undefined, response: new Response(null, { status: 500, statusText: "Boom" }) });
      expect.unreachable();
    } catch (e) {
      expect((e as ApiError).message).toBe("Boom");
    }
  });

  it("ignores non-object error bodies", () => {
    for (const error of ["<html>bad gateway</html>", ""]) {
      try {
        unwrap({ error, response: new Response(null, { status: 502, statusText: "Bad Gateway" }) });
        expect.unreachable();
      } catch (e) {
        expect((e as ApiError).message).toBe("Bad Gateway");
        expect((e as ApiError).fieldErrors).toEqual({});
      }
    }
  });

  it("empty string detail falls back to status text", () => {
    try {
      unwrap({ error: { detail: "" }, response: new Response(null, { status: 500, statusText: "Boom" }) });
      expect.unreachable();
    } catch (e) {
      expect((e as ApiError).message).toBe("Boom");
    }
  });

  it("maps empty loc key to root", () => {
    try {
      unwrap({ error: { detail: [{ loc: ["body"], msg: "bad body", type: "x" }] }, response: res(422) });
      expect.unreachable();
    } catch (e) {
      expect((e as ApiError).fieldErrors).toEqual({ root: "bad body" });
    }
  });
});
