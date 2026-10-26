/** Schedule model <-> 5-field UTC cron. Local times convert with `offset` = Date#getTimezoneOffset() (UTC = local + offset). */

export const MINUTE_STEPS = [1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30];
export const HOUR_STEPS = [1, 2, 3, 4, 6, 8, 12];
export const MAX_DAILY_TIMES = 6;

export interface Time {
  h: number;
  m: number;
}
export type Spec =
  | { mode: "manual" }
  | { mode: "minutes"; n: number }
  | { mode: "hourly"; n: number; minute: number }
  | { mode: "daily"; hours: number[]; minute: number }
  | { mode: "weekly"; days: number[]; time: Time }
  | { mode: "monthly"; days: number[]; time: Time }
  | { mode: "custom"; text: string };
export type Mode = Spec["mode"];

export const MODE_LABELS: Record<Mode, string> = {
  manual: "Manual only",
  minutes: "Every N minutes",
  hourly: "Hourly",
  daily: "Daily",
  weekly: "Weekly",
  monthly: "Monthly",
  custom: "Custom",
};

export function defaultSpec(mode: Mode, current?: string | null): Spec {
  switch (mode) {
    case "manual": return { mode };
    case "minutes": return { mode, n: 15 };
    case "hourly": return { mode, n: 1, minute: 0 };
    case "daily": return { mode, hours: [3], minute: 0 };
    case "weekly": return { mode, days: [0], time: { h: 3, m: 0 } };
    case "monthly": return { mode, days: [1], time: { h: 3, m: 0 } };
    case "custom": return { mode, text: current ?? "" };
  }
}

const mod = (a: number, n: number) => ((a % n) + n) % n;
/** Shift a time by `delta` minutes; `day` is the day carry (-1, 0, +1). */
function shift(t: Time, delta: number): Time & { day: number } {
  const total = t.h * 60 + t.m + delta;
  const day = Math.floor(total / 1440);
  const r = mod(total, 1440);
  return { h: Math.floor(r / 60), m: r % 60, day };
}
const uniqSorted = (a: number[]) => [...new Set(a)].sort((x, y) => x - y);

export interface Built {
  cron: string | null;
  /** Monthly day was not representable in UTC (day 29+ after conversion); the entered time was kept as UTC. */
  utcFallback?: boolean;
}

export function build(spec: Spec, offset: number): Built {
  switch (spec.mode) {
    case "manual": return { cron: null };
    case "custom": return { cron: spec.text === "" ? null : spec.text };
    case "minutes": return { cron: spec.n === 1 ? "* * * * *" : `*/${spec.n} * * * *` };
    case "hourly": {
      const z = shift({ h: 0, m: spec.minute }, offset);
      // Runs land on local hours divisible by n counted from local midnight.
      return { cron: `${z.m} ${spec.n === 1 ? "*" : `${mod(z.h, spec.n)}-23/${spec.n}`} * * *` };
    }
    case "daily": {
      const hs = uniqSorted(spec.hours.map((h) => shift({ h, m: spec.minute }, offset).h));
      const m = shift({ h: 0, m: spec.minute }, offset).m;
      return { cron: `${m} ${hs.join(",")} * * *` };
    }
    case "weekly": {
      const u = shift(spec.time, offset);
      const days = uniqSorted(spec.days.map((d) => mod(d + u.day, 7)));
      return { cron: `${u.m} ${u.h} * * ${days.join(",")}` };
    }
    case "monthly": {
      const u = shift(spec.time, offset);
      const days = spec.days.map((d) => d + u.day);
      // Local day 1 that lands on the previous UTC day is the last UTC day of the month ("L").
      if (days.some((d) => d < 0 || d > 28)) {
        return { cron: `${spec.time.m} ${spec.time.h} ${uniqSorted(spec.days).join(",")} * *`, utcFallback: true };
      }
      return { cron: `${u.m} ${u.h} ${uniqSorted(days).map((d) => (d === 0 ? "L" : String(d))).join(",")} * *` };
    }
  }
}

/** Local-time version of the cron, for plain-English description only. */
export const buildLocal = (spec: Spec): string | null => build(spec, 0).cron;

const intIn = (s: string, lo: number, hi: number): number | null => {
  if (!/^\d+$/.test(s)) return null;
  const n = Number(s);
  return n >= lo && n <= hi ? n : null;
};
const intList = (s: string, lo: number, hi: number): number[] | null => {
  const out: number[] = [];
  for (const p of s.split(",")) {
    const n = intIn(p, lo, hi);
    if (n === null) return null;
    out.push(n);
  }
  return out;
};

function parseBuilder(value: string, offset: number): Spec | null {
  const f = value.trim().split(/\s+/);
  if (f.length !== 5) return null;
  const [mi = "", ho = "", dom = "", mon = "", dow = ""] = f;
  if (mon !== "*") return null;
  if (ho === "*" && dom === "*" && dow === "*") {
    if (mi === "*") return { mode: "minutes", n: 1 };
    const s = /^\*\/(\d+)$/.exec(mi);
    if (s) {
      const n = Number(s[1]);
      return MINUTE_STEPS.includes(n) && n > 1 ? { mode: "minutes", n } : null;
    }
    const m = intIn(mi, 0, 59);
    return m === null ? null : { mode: "hourly", n: 1, minute: mod(m - offset, 60) };
  }
  const minute = intIn(mi, 0, 59);
  if (minute === null) return null;
  if (dom === "*" && dow === "*") {
    const s = /^(?:\*|\d+-23)\/(\d+)$/.exec(ho);
    if (s) {
      const n = Number(s[1]);
      return HOUR_STEPS.includes(n) && n > 1 ? { mode: "hourly", n, minute: mod(minute - offset, 60) } : null;
    }
    const hs = intList(ho, 0, 23);
    if (!hs) return null;
    return {
      mode: "daily",
      hours: uniqSorted(hs.map((h) => shift({ h, m: minute }, -offset).h)),
      minute: shift({ h: hs[0] ?? 0, m: minute }, -offset).m,
    };
  }
  const h = intIn(ho, 0, 23);
  if (h === null) return null;
  const local = shift({ h, m: minute }, -offset);
  const time = { h: local.h, m: local.m };
  if (dom === "*") {
    const ds = intList(dow, 0, 7);
    return ds ? { mode: "weekly", days: uniqSorted(ds.map((d) => mod(d + local.day, 7))), time } : null;
  }
  if (dow === "*") {
    const ds = dom.split(",").map((p) => (p === "L" ? 0 : intIn(p, 1, 31)));
    if (ds.length === 0 || ds.includes(null)) return null;
    const days = (ds as number[]).map((d) => d + local.day);
    return days.every((d) => d >= 1 && d <= 28) ? { mode: "monthly", days: uniqSorted(days), time } : null;
  }
  return null;
}

/** Existing value -> editor state. Anything not exactly reproducible by the builder becomes Custom. */
export function parse(value: string | null, offset: number): Spec {
  if (value === null || value.trim() === "") return { mode: "manual" };
  const spec = parseBuilder(value, offset);
  if (spec && build(spec, offset).cron === value) return spec;
  return { mode: "custom", text: value };
}

// ---- next-run matcher (UTC) ----

const ALIASES: Record<string, string> = {
  "@hourly": "0 * * * *",
  "@daily": "0 0 * * *",
  "@midnight": "0 0 * * *",
  "@weekly": "0 0 * * 0",
  "@monthly": "0 0 1 * *",
  "@yearly": "0 0 1 1 *",
  "@annually": "0 0 1 1 *",
};

export const isAlias = (t: string): boolean => t.trim().toLowerCase() in ALIASES;

function parseField(s: string, lo: number, hi: number): Set<number> | null {
  const out = new Set<number>();
  for (const part of s.split(",")) {
    const m = /^(\*|\d+(?:-\d+)?)(?:\/(\d+))?$/.exec(part);
    const range = m?.[1];
    if (!m || !range) return null;
    let a: number, b: number;
    if (range === "*") [a, b] = [lo, hi];
    else if (range.includes("-")) {
      const [x = 0, y = 0] = range.split("-").map(Number);
      [a, b] = [x, y];
    } else {
      a = Number(range);
      b = m[2] ? hi : a;
    }
    const step = m[2] ? Number(m[2]) : 1;
    if (step < 1 || a < lo || b > hi || a > b) return null;
    for (let v = a; v <= b; v += step) out.add(v);
  }
  return out;
}

export interface Matcher {
  min: number[];
  hour: number[];
  dom: Set<number>;
  /** Day-of-month list contains `L` (last day of month). */
  domL: boolean;
  mon: Set<number>;
  dow: Set<number>;
  domStar: boolean;
  dowStar: boolean;
}

export function parseCron(expr: string): Matcher | null {
  const t = expr.trim();
  const f = (ALIASES[t.toLowerCase()] ?? t).split(/\s+/);
  if (f.length !== 5) return null;
  const [fm = "", fh = "", fd = "", fo = "", fw = ""] = f;
  const mi = parseField(fm, 0, 59);
  const ho = parseField(fh, 0, 23);
  const domParts = fd.split(",");
  const domL = domParts.includes("L");
  const domRest = domParts.filter((p) => p !== "L").join(",");
  const dom = domRest === "" ? (domL ? new Set<number>() : null) : parseField(domRest, 1, 31);
  const mon = parseField(fo, 1, 12);
  const dow = parseField(fw, 0, 7);
  if (!mi || !ho || !dom || !mon || !dow) return null;
  return {
    min: [...mi].sort((a, b) => a - b),
    hour: [...ho].sort((a, b) => a - b),
    dom,
    domL,
    mon,
    dow: new Set([...dow].map((d) => d % 7)),
    domStar: fd === "*",
    dowStar: fw === "*",
  };
}

/** Next `count` run instants (ms) strictly after `from`, scanning up to ~1 year of UTC days. */
export function nextRuns(expr: string, from: number, count = 4): number[] {
  const c = parseCron(expr);
  if (!c) return [];
  const out: number[] = [];
  const start = new Date(from);
  const day0 = Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate());
  for (let i = 0; i <= 400 && out.length < count; i++) {
    const base = day0 + i * 86400000;
    const d = new Date(base);
    if (!c.mon.has(d.getUTCMonth() + 1)) continue;
    const last = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate();
    const domOk = c.dom.has(d.getUTCDate()) || (c.domL && d.getUTCDate() === last);
    const dowOk = c.dow.has(d.getUTCDay());
    const ok = c.domStar && c.dowStar ? true : c.domStar ? dowOk : c.dowStar ? domOk : domOk || dowOk;
    if (!ok) continue;
    for (const h of c.hour) {
      for (const m of c.min) {
        const t = base + (h * 60 + m) * 60000;
        if (t > from && out.length < count) out.push(t);
      }
    }
  }
  return out;
}

export function localOffset(): number {
  return new Date().getTimezoneOffset();
}
export function localTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "local time";
  } catch {
    return "local time";
  }
}

export function formatRun(t: number, now: number): string {
  const when = new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(t));
  const mins = Math.round((t - now) / 60000);
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const rel = mins < 60 ? rtf.format(mins, "minute") : mins < 1440 ? rtf.format(Math.round(mins / 60), "hour") : rtf.format(Math.round(mins / 1440), "day");
  return `${when} · ${rel}`;
}
