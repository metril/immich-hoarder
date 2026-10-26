import { useRef } from "react";
import { FormField, inputClass } from "../../components/common/FormField";
import { ALBUM_FIELDS } from "./schema";

export function AlbumTemplateField({ value, onChange, error }: { value: string; onChange: (v: string) => void; error?: string }) {
  const ref = useRef<HTMLInputElement>(null);
  const insert = (name: string) => {
    const el = ref.current;
    const at = el?.selectionStart ?? value.length;
    const end = el?.selectionEnd ?? at;
    onChange(`${value.slice(0, at)}{${name}}${value.slice(end)}`);
    el?.focus();
  };
  return (
    <div className="grid gap-2">
      <FormField label="Album template" error={error} hint="Empty = no album">
        <input ref={ref} className={`${inputClass} font-mono`} value={value} onChange={(e) => onChange(e.target.value)} placeholder="{subreddit}" />
      </FormField>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Insert album field">
        {ALBUM_FIELDS.map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => insert(f)}
            className="rounded-full border px-3 py-1 font-mono text-xs transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
          >
            {`{${f}}`}
          </button>
        ))}
      </div>
    </div>
  );
}
