import cronstrue from "cronstrue";
import { FormField, inputClass } from "../../components/common/FormField";
import { CRON_PRESETS } from "./schema";

function describe(v: string): string | null {
  try {
    return cronstrue.toString(v, { use24HourTimeFormat: true });
  } catch {
    return null;
  }
}

export function CronField({ value, onChange, error }: { value: string | null; onChange: (v: string | null) => void; error?: string }) {
  const text = value ?? "";
  const special = text.trim().startsWith("@");
  const desc = text.trim() && !special ? describe(text) : null;
  const invalid = text.trim() !== "" && !special && desc === null;
  const hint = !text.trim() ? "Off: only runs when started manually" : special ? "Special schedule — the server will validate" : desc;
  return (
    <div className="grid gap-2">
      <FormField label="Schedule (cron)" error={error ?? (invalid ? "Invalid cron expression" : undefined)} hint={hint}>
        <input
          className={`${inputClass} font-mono`}
          value={text}
          placeholder="0 3 * * *"
          spellCheck={false}
          onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
        />
      </FormField>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Schedule presets">
        {CRON_PRESETS.map((p) => (
          <button
            key={p.label}
            type="button"
            aria-pressed={value === p.value}
            onClick={() => onChange(p.value)}
            className="rounded-full border px-2.5 py-1 text-xs hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring aria-pressed:bg-accent"
          >
            {p.label}
          </button>
        ))}
      </div>
    </div>
  );
}
