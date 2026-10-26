import { useId } from "react";
import { useUsableCredentials } from "./pickers";
import type { SourceNotify } from "./hooks";

const EVENTS: { value: SourceNotify["on"][number]; label: string }[] = [
  { value: "success", label: "On success" },
  { value: "failure", label: "On failure" },
  { value: "new_items", label: "On new items" },
];

const toggle = <T,>(list: T[], item: T) => (list.includes(item) ? list.filter((x) => x !== item) : [...list, item]);

export function NotifyField({ value, onChange, error, keep }: { value: SourceNotify; onChange: (v: SourceNotify) => void; error?: string; keep?: number[] }) {
  const errId = useId();
  const apprise = useUsableCredentials(undefined, keep).filter((c) => c.kind === "apprise");
  return (
    <fieldset className="grid gap-3" aria-describedby={error ? errId : undefined}>
      <legend className="sr-only">Notifications</legend>
      {apprise.length === 0 ? (
        <p className="text-sm text-muted-foreground">No Apprise credentials available.</p>
      ) : (
        <div className="grid gap-2" role="group" aria-label="Notify credentials">
          {apprise.map((c) => (
            <label key={c.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={value.credential_ids.includes(c.id)}
                onChange={() => onChange({ ...value, credential_ids: toggle(value.credential_ids, c.id) })}
              />
              {c.name}
            </label>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-4" role="group" aria-label="Notify events">
        {EVENTS.map((e) => (
          <label key={e.value} className="flex items-center gap-1.5 text-sm">
            <input type="checkbox" checked={value.on.includes(e.value)} onChange={() => onChange({ ...value, on: toggle(value.on, e.value) })} />
            {e.label}
          </label>
        ))}
      </div>
      {error && <p id={errId} role="alert" className="text-sm text-destructive">{error}</p>}
    </fieldset>
  );
}
