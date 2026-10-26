import { useState } from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Truncate } from "@/components/ui/truncate";
import { Input } from "@/components/ui/input";
import { FormField } from "../../components/common/FormField";
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
    <fieldset className="grid min-w-0 gap-4 rounded-lg border p-4">
      <legend className="px-1 text-sm font-medium">Rate limits per category</legend>
      {entries.length === 0 && <p className="text-sm text-muted-foreground">No overrides; extractor defaults apply.</p>}
      {entries.map(([cat, rl]) => (
        <div key={cat} className="grid gap-3 rounded-lg border p-3 sm:grid-cols-[minmax(0,1fr)_repeat(3,6.5rem)_auto] sm:items-end">
          <Truncate className="font-mono text-sm">{cat}</Truncate>
          {FIELDS.map(([k, label]) => {
            const msg = errors?.[cat]?.[k]?.message;
            return (
            <label key={k} className="grid gap-1.5 text-xs">
              <span>
                {label}
                <span className="sr-only"> for {cat}</span>
              </span>
              <Input
                type="number"
                step={k === "retries" ? 1 : 0.1}
                min={0}
                value={Number.isNaN(rl[k]) ? "" : rl[k]}
                aria-invalid={msg ? true : undefined}
                onChange={(ev) => onChange({ ...value, [cat]: { ...rl, [k]: ev.target.valueAsNumber } })}
              />
              {msg && <span role="alert" className="text-destructive">{msg}</span>}
            </label>
            );
          })}
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Remove ${cat}`}
            onClick={() => {
              const { [cat]: _gone, ...rest } = value;
              void _gone;
              onChange(rest);
            }}
          >
            <Trash2 aria-hidden />
          </Button>
        </div>
      ))}
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <FormField label="New category" error={error}>
            <Input
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
        <Button variant="outline" onClick={add}>
          Add category
        </Button>
      </div>
    </fieldset>
  );
}
