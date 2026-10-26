import { describe, expect, it } from "vitest";
import { build, nextRuns, parse, parseCron, type Spec } from "./cron";

// offset = getTimezoneOffset(): UTC-5 -> 300, UTC+5:30 -> -330, UTC+10 -> -600
const OFFSETS = [0, 300, -330, -600, 540];

describe("build/parse", () => {
  const specs: Spec[] = [
    { mode: "manual" },
    { mode: "minutes", n: 1 },
    { mode: "minutes", n: 15 },
    { mode: "hourly", n: 1, minute: 0 },
    { mode: "hourly", n: 6, minute: 30 },
    { mode: "daily", hours: [3], minute: 0 },
    { mode: "daily", hours: [1, 9, 22], minute: 45 },
    { mode: "weekly", days: [0], time: { h: 3, m: 0 } },
    { mode: "weekly", days: [1, 3, 5], time: { h: 23, m: 30 } },
    { mode: "weekly", days: [0, 6], time: { h: 0, m: 15 } },
    { mode: "monthly", days: [2, 15], time: { h: 12, m: 0 } },
  ];

  it.each(OFFSETS)("round-trips specs at offset %i", (off) => {
    for (const s of specs) {
      const { cron } = build(s, off);
      expect(parse(cron, off)).toEqual(s);
      expect(build(parse(cron, off), off).cron).toBe(cron);
    }
  });

  it("converts local to UTC with day carry", () => {
    // 22:00 Mon local at UTC-5 -> 03:00 Tue UTC
    expect(build({ mode: "weekly", days: [1], time: { h: 22, m: 0 } }, 300).cron).toBe("0 3 * * 2");
    // 02:00 Sun local at UTC+10 -> 16:00 Sat UTC
    expect(build({ mode: "weekly", days: [0], time: { h: 2, m: 0 } }, -600).cron).toBe("0 16 * * 6");
    expect(build({ mode: "daily", hours: [3, 15], minute: 0 }, 0).cron).toBe("0 3,15 * * *");
  });

  it("keeps monthly as UTC when the day would leave 1..28", () => {
    const b = build({ mode: "monthly", days: [1], time: { h: 2, m: 0 } }, -600);
    expect(b.utcFallback).toBe(true);
    expect(b.cron).toBe("0 2 1 * *");
  });

  it("unknown patterns become custom", () => {
    for (const v of ["@daily", "*/7 * * * *", "0 9-17 * * 1-5", "0 3 1 6 *", "0 0 1 * 1", "0 */5 * * *", "0 3 * * 7", "0 3,1 * * *"]) {
      expect(parse(v, 0)).toEqual({ mode: "custom", text: v });
    }
  });

  it("parses the common presets", () => {
    expect(parse("0 * * * *", 0)).toEqual({ mode: "hourly", n: 1, minute: 0 });
    expect(parse("0 */6 * * *", 0)).toEqual({ mode: "hourly", n: 6, minute: 0 });
    expect(parse("0 3 * * 0", 0)).toEqual({ mode: "weekly", days: [0], time: { h: 3, m: 0 } });
  });
});

describe("nextRuns", () => {
  const from = Date.UTC(2026, 9, 26, 10, 30); // Mon 2026-10-26 10:30 UTC
  const iso = (a: number[]) => a.map((t) => new Date(t).toISOString().slice(0, 16));

  it("handles steps and lists", () => {
    expect(iso(nextRuns("*/20 * * * *", from, 3))).toEqual(["2026-10-26T10:40", "2026-10-26T11:00", "2026-10-26T11:20"]);
    expect(iso(nextRuns("0 3,15 * * *", from, 3))).toEqual(["2026-10-26T15:00", "2026-10-27T03:00", "2026-10-27T15:00"]);
  });

  it("handles weekdays with Sunday as 0 or 7", () => {
    expect(iso(nextRuns("0 3 * * 0", from, 2))).toEqual(["2026-11-01T03:00", "2026-11-08T03:00"]);
    expect(iso(nextRuns("0 3 * * 7", from, 1))).toEqual(["2026-11-01T03:00"]);
    expect(iso(nextRuns("0 9 * * 1-5", from, 2))).toEqual(["2026-10-27T09:00", "2026-10-28T09:00"]);
  });

  it("handles monthly, aliases and sparse dates", () => {
    expect(iso(nextRuns("0 3 1 * *", from, 2))).toEqual(["2026-11-01T03:00", "2026-12-01T03:00"]);
    expect(iso(nextRuns("@daily", from, 1))).toEqual(["2026-10-27T00:00"]);
    expect(iso(nextRuns("@yearly", from, 1))).toEqual(["2027-01-01T00:00"]);
    expect(nextRuns("0 0 29 2 *", from, 1)).toEqual([]); // beyond the ~1y scan window
  });

  it("rejects bad input", () => {
    expect(parseCron("nope")).toBeNull();
    expect(parseCron("61 * * * *")).toBeNull();
    expect(parseCron("@reboot")).toBeNull();
    expect(nextRuns("* * *", from)).toEqual([]);
  });
});
