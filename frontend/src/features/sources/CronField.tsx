import { useEffect, useState } from "react";
import { Plus, X } from "lucide-react";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Select } from "../../components/ui/select";
import { cn } from "../../components/ui/cn";
import {
  HOUR_STEPS, MAX_DAILY_TIMES, MINUTE_STEPS, MODE_LABELS, build, buildLocal, defaultSpec, formatRun, localOffset, localTimeZone,
  isAlias, nextRuns, parse, parseCron, type Mode, type Spec, type Time,
} from "./cron";

const WEEK = [
  { d: 1, short: "Mon", long: "Monday" }, { d: 2, short: "Tue", long: "Tuesday" }, { d: 3, short: "Wed", long: "Wednesday" },
  { d: 4, short: "Thu", long: "Thursday" }, { d: 5, short: "Fri", long: "Friday" }, { d: 6, short: "Sat", long: "Saturday" },
  { d: 0, short: "Sun", long: "Sunday" },
];
const MONTH_DAYS = Array.from({ length: 28 }, (_, i) => i + 1);
const pad = (n: number) => String(n).padStart(2, "0");
const toStr = (t: Time) => `${pad(t.h)}:${pad(t.m)}`;
const fromStr = (s: string): Time | null => {
  const m = /^(\d{2}):(\d{2})/.exec(s);
  return m ? { h: Number(m[1]), m: Number(m[2]) } : null;
};

function Toggle({ pressed, onClick, label, children, className }: { pressed: boolean; onClick: () => void; label?: string; children: string; className?: string }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      aria-label={label}
      onClick={onClick}
      className={cn(
        "h-9 min-w-9 rounded-md border px-2.5 text-sm transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring aria-pressed:border-primary aria-pressed:bg-primary aria-pressed:text-primary-foreground",
        className,
      )}
    >
      {children}
    </button>
  );
}

function nextFreeHour(hours: number[]): number {
  const start = ((hours[hours.length - 1] ?? 0) + 6) % 24;
  for (let i = 0; i < 24; i++) {
    const h = (start + i) % 24;
    if (!hours.includes(h)) return h;
  }
  return start;
}

function toggleIn(list: number[], v: number): number[] {
  if (!list.includes(v)) return [...list, v];
  return list.length > 1 ? list.filter((x) => x !== v) : list;
}

/** cronstrue is lazy-loaded; undefined while loading, null when it cannot describe. */
function useDescription(text: string | null): string | null | undefined {
  const [state, setState] = useState<{ key: string; desc: string | null } | null>(null);
  useEffect(() => {
    if (!text) return;
    let live = true;
    void import("cronstrue").then(({ default: cronstrue }) => {
      let desc: string | null;
      try {
        desc = cronstrue.toString(text, { use24HourTimeFormat: true });
      } catch {
        desc = null;
      }
      if (live) setState({ key: text, desc });
    });
    return () => {
      live = false;
    };
  }, [text]);
  if (!text) return null;
  return state?.key === text ? state.desc : undefined;
}

export function CronField({ value, onChange, error, allowManual = true }: { value: string | null; onChange: (v: string | null) => void; error?: string; allowManual?: boolean }) {
  const offset = localOffset();
  const [spec, setSpec] = useState<Spec>(() => parse(value, offset));
  const built = build(spec, offset);
  if ((built.cron?.trim() ?? "") !== (value?.trim() ?? "")) setSpec(parse(value, offset));

  const [now] = useState(() => Date.now());
  const update = (s: Spec) => {
    setSpec(s);
    onChange(build(s, offset).cron);
  };

  const isCustom = spec.mode === "custom";
  const text = built.cron;
  const alias = !!text && isAlias(text);
  const fieldCount = text ? text.trim().split(/\s+/).length : 0;
  const parsed = text ? parseCron(text) : null;
  const desc = useDescription(text && !alias ? (isCustom ? text : buildLocal(spec)) : null);
  const invalid = isCustom && !!text && !alias && (fieldCount !== 5 || (!parsed && desc === null));
  const runs = text && parsed && !invalid ? nextRuns(text, now, 4) : [];
  const tz = localTimeZone();

  return (
    <fieldset className="grid gap-5 border-0 p-0">
      <legend className="mb-3 text-sm font-medium">Schedule</legend>
      <div className="grid gap-1.5">
        <Label htmlFor="sched-mode">Frequency</Label>
        <Select id="sched-mode" value={spec.mode} onChange={(e) => update(defaultSpec(e.target.value as Mode, text))}>
          {(Object.keys(MODE_LABELS) as Mode[]).filter((m) => allowManual || m !== "manual").map((m) => (
            <option key={m} value={m}>{MODE_LABELS[m]}</option>
          ))}
        </Select>
      </div>

      {spec.mode === "minutes" && (
        <div className="grid gap-1.5">
          <Label htmlFor="sched-n">Every (minutes)</Label>
          <Select id="sched-n" value={spec.n} onChange={(e) => update({ ...spec, n: Number(e.target.value) })}>
            {MINUTE_STEPS.map((n) => <option key={n} value={n}>{n}</option>)}
          </Select>
        </div>
      )}

      {spec.mode === "hourly" && (
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="grid gap-1.5">
            <Label htmlFor="sched-hn">Every (hours)</Label>
            <Select id="sched-hn" value={spec.n} onChange={(e) => update({ ...spec, n: Number(e.target.value) })}>
              {HOUR_STEPS.map((n) => <option key={n} value={n}>{n}</option>)}
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="sched-hm">At minute</Label>
            <Input
              id="sched-hm"
              type="number"
              min={0}
              max={59}
              value={spec.minute}
              onChange={(e) => update({ ...spec, minute: Math.min(59, Math.max(0, Math.floor(Number(e.target.value) || 0))) })}
            />
          </div>
        </div>
      )}

      {spec.mode === "daily" && (
        <div className="grid gap-2">
          <Label htmlFor="sched-t0">Run at</Label>
          {spec.hours.map((h, i) => (
            <div key={i} className="flex items-center gap-2">
              <Input
                id={`sched-t${i}`}
                type="time"
                aria-label={i === 0 ? undefined : `Time ${i + 1}`}
                className="w-auto"
                value={toStr({ h, m: spec.minute })}
                onChange={(e) => {
                  const t = fromStr(e.target.value);
                  if (t && !spec.hours.some((x, j) => j !== i && x === t.h)) update({ ...spec, minute: t.m, hours: spec.hours.map((x, j) => (j === i ? t.h : x)) });
                }}
              />
              {spec.hours.length > 1 && (
                <Button type="button" variant="ghost" size="icon" aria-label={`Remove time ${i + 1}`} onClick={() => update({ ...spec, hours: spec.hours.filter((_, j) => j !== i) })}>
                  <X />
                </Button>
              )}
            </div>
          ))}
          <div className="flex flex-wrap items-center gap-3">
            {spec.hours.length < MAX_DAILY_TIMES && (
              <Button type="button" variant="outline" size="sm" onClick={() => update({ ...spec, hours: [...spec.hours, nextFreeHour(spec.hours)] })}>
                <Plus /> Add time
              </Button>
            )}
            <span className="text-xs text-muted-foreground">Extra times share the same minute.</span>
          </div>
        </div>
      )}

      {spec.mode === "weekly" && (
        <>
          <div className="grid gap-1.5">
            <span className="text-sm font-medium" id="sched-days">On</span>
            <div role="group" aria-labelledby="sched-days" className="flex flex-wrap gap-2">
              {WEEK.map((w) => (
                <Toggle key={w.d} label={w.long} pressed={spec.days.includes(w.d)} onClick={() => update({ ...spec, days: toggleIn(spec.days, w.d) })}>
                  {w.short}
                </Toggle>
              ))}
            </div>
          </div>
          <TimeInput value={spec.time} onChange={(time) => update({ ...spec, time })} />
        </>
      )}

      {spec.mode === "monthly" && (
        <>
          <div className="grid gap-1.5">
            <span className="text-sm font-medium" id="sched-mdays">On day of month</span>
            <div role="group" aria-labelledby="sched-mdays" className="grid grid-cols-7 gap-1.5 sm:max-w-sm">
              {MONTH_DAYS.map((d) => (
                <Toggle key={d} label={`Day ${d}`} pressed={spec.days.includes(d)} onClick={() => update({ ...spec, days: toggleIn(spec.days, d) })} className="px-0">
                  {String(d)}
                </Toggle>
              ))}
            </div>
          </div>
          <TimeInput value={spec.time} onChange={(time) => update({ ...spec, time })} />
          {built.utcFallback && (
            <p className="text-xs text-muted-foreground">This day and time cannot be expressed in UTC from {tz}, so the time you entered is used as UTC instead.</p>
          )}
        </>
      )}

      {spec.mode === "custom" && (
        <div className="grid gap-1.5">
          <Label htmlFor="sched-cron">Schedule (cron)</Label>
          <Input
            id="sched-cron"
            className="font-mono"
            value={spec.text}
            placeholder="0 3 * * *  or  @daily"
            spellCheck={false}
            aria-invalid={error || invalid ? true : undefined}
            aria-describedby="sched-cron-hint"
            onChange={(e) => update({ mode: "custom", text: e.target.value })}
          />
          <p id="sched-cron-hint" className="text-xs text-muted-foreground">5 fields, evaluated in UTC (Sunday = 0). Aliases @hourly, @daily, @weekly, @monthly, @yearly work.</p>
        </div>
      )}

      {(error || invalid) && (
        <p role="alert" className="text-sm text-destructive">{error ?? "Invalid cron expression"}</p>
      )}

      <div className="grid gap-2 rounded-lg border bg-muted/30 p-4 text-sm" aria-live="polite">
        {!text ? (
          <p>Off: only runs when started manually.</p>
        ) : (
          <>
            {desc ? <p className="font-medium">{desc}{isCustom ? " (UTC)" : ""}</p> : alias ? <p className="font-medium">{text.trim()} (UTC)</p> : null}
            {runs.length > 0 && (
              <div>
                <p className="text-xs text-muted-foreground">Next runs:</p>
                <ul className="mt-1 grid gap-0.5">
                  {runs.map((t) => <li key={t}>{formatRun(t, now)}</li>)}
                </ul>
              </div>
            )}
            {parsed && !invalid && runs.length === 0 && <p className="text-xs text-muted-foreground">No runs in the next year</p>}
            {!parsed && !invalid && desc !== undefined && <p className="text-xs text-muted-foreground">Next runs can't be previewed; the server will validate.</p>}
          </>
        )}
        {!isCustom && spec.mode !== "manual" && !built.utcFallback && (
          <p className="text-xs text-muted-foreground">Times in {tz}; stored as UTC (DST changes may shift runs by 1 hour (and across midnight)).</p>
        )}
      </div>
    </fieldset>
  );
}

function TimeInput({ value, onChange }: { value: Time; onChange: (t: Time) => void }) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor="sched-time">At</Label>
      <Input id="sched-time" type="time" className="w-auto" value={toStr(value)} onChange={(e) => { const t = fromStr(e.target.value); if (t) onChange(t); }} />
    </div>
  );
}
