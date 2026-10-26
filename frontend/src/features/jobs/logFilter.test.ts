import { describe, expect, it } from "vitest";
import type { LogLine } from "../../live/types";
import { filterLog } from "./logFilter";

const L = (id: number, level: LogLine["level"], msg: string, logger?: string): LogLine => ({ type: "log", id, ts: "t", job_id: 1, level, msg, logger });
const lines = [L(1, "debug", "a"), L(2, "info", "Hello"), L(3, "warn", "x", "Net"), L(4, "error", "boom")];

describe("filterLog", () => {
  it("filters by min level", () => {
    expect(filterLog(lines, { minLevel: "warn", query: "" }).map((l) => l.id)).toEqual([3, 4]);
  });
  it("matches msg and logger case-insensitively", () => {
    expect(filterLog(lines, { minLevel: "trace", query: "HELLO" }).map((l) => l.id)).toEqual([2]);
    expect(filterLog(lines, { minLevel: "trace", query: "net" }).map((l) => l.id)).toEqual([3]);
  });
});
