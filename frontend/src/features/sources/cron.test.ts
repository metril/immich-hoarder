import { describe, expect, it } from "vitest";
import { build, nextRuns, parse, parseCron, type Spec } from "./cron";

// offset = getTimezoneOffset(): UTC-5 -> 300, UTC+5:30 -> -330, UTC+10 -> -600
const OFFSETS = [0, 300, -330, -600, 540, -345, 210];

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
    { mode: "monthly", days: [1], time: { h: 3, m: 0 } },
    { mode: "hourly", n: 4, minute: 10 },
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

  it("maps local day 1 east of UTC to L", () => {
    expect(build({ mode: "monthly", days: [1], time: { h: 3, m: 0 } }, -600).cron).toBe("0 17 L * *");
    expect(parse("0 17 L * *", -600)).toEqual({ mode: "monthly", days: [1], time: { h: 3, m: 0 } });
  });

  it("keeps monthly as UTC when the day is not representable", () => {
    const b = build({ mode: "monthly", days: [28], time: { h: 23, m: 0 } }, 300);
    expect(b.utcFallback).toBe(true);
    expect(b.cron).toBe("0 23 28 * *");
  });

  it("hourly honours the timezone", () => {
    expect(build({ mode: "hourly", n: 1, minute: 0 }, -345).cron).toBe("15 * * * *");
    expect(build({ mode: "hourly", n: 6, minute: 0 }, 300).cron).toBe("0 5-23/6 * * *");
  });

  it("unknown patterns become custom", () => {
    for (const v of ["@daily", "*/7 * * * *", "0 9-17 * * 1-5", "0 3 1 6 *", "0 0 1 * 1", "0 */5 * * *", "0 3 * * 7", "0 3,1 * * *"]) {
      expect(parse(v, 0)).toEqual({ mode: "custom", text: v });
    }
  });

  it("parses the common presets", () => {
    expect(parse("0 * * * *", 0)).toEqual({ mode: "hourly", n: 1, minute: 0 });
    expect(parse("0 0-23/6 * * *", 0)).toEqual({ mode: "hourly", n: 6, minute: 0 });
    expect(parse("0 3 * * 0", 0)).toEqual({ mode: "weekly", days: [0], time: { h: 3, m: 0 } });
  });
});

describe("local time of next run", () => {
  const from = Date.UTC(2026, 0, 10, 12, 0);
  const local = (t: number, off: number) => new Date(t - off * 60000);
  const hm = (d: Date) => `${d.getUTCHours()}:${d.getUTCMinutes()}`;

  it.each([-345, 210, -330, 300, -600, 0])("next runs match the entered local time at offset %i", (off) => {
    const daily = nextRuns(build({ mode: "daily", hours: [3, 15], minute: 20 }, off).cron ?? "", from, 4);
    expect(new Set(daily.map((t) => hm(local(t, off))))).toEqual(new Set(["3:20", "15:20"]));

    const weekly = nextRuns(build({ mode: "weekly", days: [1], time: { h: 22, m: 10 } }, off).cron ?? "", from, 3);
    for (const t of weekly) expect([hm(local(t, off)), local(t, off).getUTCDay()]).toEqual(["22:10", 1]);

    const monthly = nextRuns(build({ mode: "monthly", days: [1], time: { h: 3, m: 5 } }, off).cron ?? "", from, 3);
    expect(monthly).toHaveLength(3);
    for (const t of monthly) expect([hm(local(t, off)), local(t, off).getUTCDate()]).toEqual(["3:5", 1]);

    const hourly = nextRuns(build({ mode: "hourly", n: 6, minute: 25 }, off).cron ?? "", from, 8);
    for (const t of hourly) {
      const d = local(t, off);
      expect(d.getUTCHours() % 6).toBe(0);
      expect(d.getUTCMinutes()).toBe(25);
    }
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
    expect(iso(nextRuns("0 0 L * *", from, 2))).toEqual(["2026-10-31T00:00", "2026-11-30T00:00"]);
    expect(nextRuns("0 0 29 2 *", from, 1)).toEqual([]); // beyond the ~1y scan window
  });

  it("rejects bad input", () => {
    expect(parseCron("nope")).toBeNull();
    expect(parseCron("61 * * * *")).toBeNull();
    expect(parseCron("@reboot")).toBeNull();
    expect(nextRuns("* * *", from)).toEqual([]);
  });
});
