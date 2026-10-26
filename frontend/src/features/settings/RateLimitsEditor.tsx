import { useState } from "react";
import { Trash2 } from "lucide-react";
import { FormField, inputClass } from "../../components/common/FormField";
import type { SettingsDoc } from "./hooks";

type RipSettings = NonNullable<SettingsDoc["rip"]>;
export type RateLimits = RipSettings["rate_limits"];
const FIELDS = [
  ["sleep_request", "Sleep between requests (s)"],
  ["sleep", "Sleep between items (s)"],
  ["retries", "Retries"],
] as const;

export type RateLimitErrors = Record<string, Partial<Record<(typeof FIELDS)[number][0], { message?: string }>> | undefined> | undefined;

export function RateLimitsEditor({ value, onChange, errors }: { value: RateLimits; onChange: (v: RateLimits) => void; errors?: RateLimitErrors }) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string>();
  const add = () => {
    const key = name.trim();
    if (!key) return setError("Category is required");
    if (key in value) return setError("Category already exists");
    onChange({ ...value, [key]: { sleep_request: 1, sleep: 0, retries: 4 } });
    setName("");
    setError(undefined);
  };
  const entries = Object.entries(value);
  return (
    <fieldset className="grid gap-3 rounded-md border p-3">
      <legend className="px-1 text-sm font-medium">Rate limits per category</legend>
      {entries.length === 0 && <p className="text-sm text-muted-foreground">No overrides; extractor defaults apply.</p>}
      {entries.map(([cat, rl]) => (
        <div key={cat} className="grid gap-2 rounded-md border p-2 sm:grid-cols-[1fr_repeat(3,7rem)_auto] sm:items-end">
          <span className="font-mono text-sm">{cat}</span>
          {FIELDS.map(([k, label]) => {
            const msg = errors?.[cat]?.[k]?.message;
            return (
            <label key={k} className="grid gap-1 text-xs">
              <span>
                {label}
                <span className="sr-only"> for {cat}</span>
              </span>
              <input
                type="number"
                step={k === "retries" ? 1 : 0.1}
                min={0}
                className={inputClass}
                value={Number.isNaN(rl[k]) ? "" : rl[k]}
                aria-invalid={msg ? true : undefined}
                onChange={(ev) => onChange({ ...value, [cat]: { ...rl, [k]: ev.target.valueAsNumber } })}
              />
              {msg && <span role="alert" className="text-destructive">{msg}</span>}
            </label>
            );
          })}
          <button
            type="button"
            aria-label={`Remove ${cat}`}
            onClick={() => {
              const { [cat]: _gone, ...rest } = value;
              void _gone;
              onChange(rest);
            }}
            className="inline-flex size-9 items-center justify-center rounded-md hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
          >
            <Trash2 className="size-4" aria-hidden />
          </button>
        </div>
      ))}
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <FormField label="New category" error={error}>
            <input
              className={inputClass}
              value={name}
              placeholder="e.g. reddit"
              onChange={(e) => {
                setName(e.target.value);
                setError(undefined);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  add();
                }
              }}
            />
          </FormField>
        </div>
        <button type="button" onClick={add} className="h-9 rounded-md border px-3 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring">
          Add category
        </button>
      </div>
    </fieldset>
  );
}
