import { useState } from "react";
import { FormField, inputClass } from "../../components/common/FormField";
import type { FilterSpec } from "./hooks";
import { emptyFilters, summarize } from "./schema";

type Errors = Partial<Record<keyof FilterSpec, string>>;
const UNITS = { KB: 1024, MB: 1024 * 1024 } as const;
type Unit = keyof typeof UNITS;

function NumberInput({ label, value, onChange, error, step }: {
  label: string; value: number | null | undefined; onChange: (v: number | null) => void; error?: string; step?: string;
}) {
  return (
    <FormField label={label} error={error}>
      <input
        type="number"
        min={0}
        step={step}
        className={inputClass}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      />
    </FormField>
  );
}

function BytesInput({ label, value, onChange, error }: { label: string; value: number | null | undefined; onChange: (v: number | null) => void; error?: string }) {
  const [unit, setUnit] = useState<Unit>(value && value >= UNITS.MB && value % UNITS.MB === 0 ? "MB" : "KB");
  const shown = value == null ? "" : String(Math.round((value / UNITS[unit]) * 1000) / 1000);
  const emit = (text: string, u: Unit) => onChange(text === "" || Number.isNaN(Number(text)) ? null : Math.round(Number(text) * UNITS[u]));
  return (
    <div className="grid grid-cols-[1fr_auto] items-end gap-2">
      <FormField label={label} error={error}>
        <input type="number" min={0} step="any" className={inputClass} value={shown} onChange={(e) => emit(e.target.value, unit)} />
      </FormField>
      <select
        aria-label={`${label} unit`}
        className={`${inputClass} !w-auto`}
        value={unit}
        onChange={(e) => {
          const u = e.target.value as Unit;
          setUnit(u);
          emit(shown, u);
        }}
      >
        <option value="KB">KB</option>
        <option value="MB">MB</option>
      </select>
    </div>
  );
}

function RegexInput({ label, value, onChange, error }: { label: string; value: string | null | undefined; onChange: (v: string | null) => void; error?: string }) {
  let msg = error;
  if (!msg && value) {
    try {
      new RegExp(value);
    } catch {
      msg = "Invalid regular expression";
    }
  }
  return (
    <FormField label={label} error={msg}>
      <input className={`${inputClass} font-mono`} value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)} />
    </FormField>
  );
}

export function FilterBuilder({ value, onChange, errors = {}, error }: { value: FilterSpec; onChange: (v: FilterSpec) => void; errors?: Errors; error?: string }) {
  const v = { ...emptyFilters(), ...value } as FilterSpec;
  const set = <K extends keyof FilterSpec>(k: K, x: FilterSpec[K]) => onChange({ ...v, [k]: x });
  return (
    <fieldset className="grid gap-4 rounded-md border p-3">
      <legend className="px-1 text-sm font-medium">Filters</legend>
      <section aria-label="Size" className="grid gap-2">
        <h4 className="text-xs font-semibold uppercase text-muted-foreground">Size</h4>
        <div className="grid gap-3 sm:grid-cols-2">
          <NumberInput label="Min width (px)" value={v.min_width} onChange={(x) => set("min_width", x)} error={errors.min_width} />
          <NumberInput label="Min height (px)" value={v.min_height} onChange={(x) => set("min_height", x)} error={errors.min_height} />
          <BytesInput label="Min size" value={v.min_bytes} onChange={(x) => set("min_bytes", x)} error={errors.min_bytes} />
          <BytesInput label="Max size" value={v.max_bytes} onChange={(x) => set("max_bytes", x)} error={errors.max_bytes} />
        </div>
      </section>
      <section aria-label="Aspect" className="grid gap-2">
        <h4 className="text-xs font-semibold uppercase text-muted-foreground">Aspect (width / height)</h4>
        <div className="grid gap-3 sm:grid-cols-2">
          <NumberInput label="Min aspect" step="any" value={v.aspect_min} onChange={(x) => set("aspect_min", x)} error={errors.aspect_min} />
          <NumberInput label="Max aspect" step="any" value={v.aspect_max} onChange={(x) => set("aspect_max", x)} error={errors.aspect_max} />
        </div>
      </section>
      <section aria-label="Title" className="grid gap-2">
        <h4 className="text-xs font-semibold uppercase text-muted-foreground">Title regex</h4>
        <div className="grid gap-3 sm:grid-cols-2">
          <RegexInput label="Title include" value={v.title_include} onChange={(x) => set("title_include", x)} error={errors.title_include} />
          <RegexInput label="Title exclude" value={v.title_exclude} onChange={(x) => set("title_exclude", x)} error={errors.title_exclude} />
        </div>
      </section>
      <section aria-label="Date" className="grid gap-2">
        <h4 className="text-xs font-semibold uppercase text-muted-foreground">Date</h4>
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField label="Date from" error={errors.date_from}>
            <input type="date" className={inputClass} value={v.date_from ?? ""} onChange={(e) => set("date_from", e.target.value || null)} />
          </FormField>
          <FormField label="Date to" error={errors.date_to}>
            <input type="date" className={inputClass} value={v.date_to ?? ""} onChange={(e) => set("date_to", e.target.value || null)} />
          </FormField>
        </div>
      </section>
      <div className="grid gap-3 sm:grid-cols-2">
        <NumberInput label="Max items" value={v.max_items} onChange={(x) => set("max_items", x)} error={errors.max_items} />
        <FormField label={`pHash distance: ${v.phash_distance ?? 3}`} error={errors.phash_distance} hint="0 = exact duplicates only, 3 = most tolerant">
          <input type="range" min={0} max={3} step={1} value={v.phash_distance ?? 3} onChange={(e) => set("phash_distance", Number(e.target.value))} />
        </FormField>
      </div>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <p className="text-sm text-muted-foreground" data-testid="filter-summary">{summarize(v)}</p>
    </fieldset>
  );
}
