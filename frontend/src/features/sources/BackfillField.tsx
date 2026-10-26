import { FormField, inputClass } from "../../components/common/FormField";
import type { BackfillMode } from "./hooks";

const MODES: { value: BackfillMode; label: string }[] = [
  { value: "full", label: "Full" },
  { value: "last_n", label: "Last N items" },
  { value: "since", label: "Since date" },
];

export function BackfillField({ mode, value, onModeChange, onValueChange, error }: {
  mode: BackfillMode; value: string; onModeChange: (m: BackfillMode) => void; onValueChange: (v: string) => void; error?: string;
}) {
  return (
    <fieldset className="grid gap-3">
      <legend className="mb-2 text-sm font-medium">Backfill</legend>
      <div className="flex flex-wrap gap-4">
        {MODES.map((m) => (
          <label key={m.value} className="flex items-center gap-1.5 text-sm">
            <input type="radio" name="backfill_mode" value={m.value} checked={mode === m.value} onChange={() => onModeChange(m.value)} />
            {m.label}
          </label>
        ))}
      </div>
      {mode === "last_n" && (
        <FormField label="Item count" error={error}>
          <input type="number" min={1} step={1} className={inputClass} value={value} onChange={(e) => onValueChange(e.target.value)} />
        </FormField>
      )}
      {mode === "since" && (
        <FormField label="Since date" error={error}>
          <input type="date" className={inputClass} value={value} onChange={(e) => onValueChange(e.target.value)} />
        </FormField>
      )}
      {mode === "full" && error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    </fieldset>
  );
}
