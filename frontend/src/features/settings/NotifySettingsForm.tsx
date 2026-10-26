import { Eye, EyeOff, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Controller } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { inputClass } from "../../components/common/FormField";
import { useApiForm } from "../../components/common/useApiForm";
import { SaveBar } from "./fields";
import { useSaveSettings, type SettingsDoc } from "./hooks";

const EVENTS = [
  ["success", "Success"],
  ["failure", "Failure"],
  ["new_items", "New items"],
] as const;
const schema = z.object({
  notify: z.object({
    on: z.array(z.enum(["success", "failure", "new_items"])),
    urls: z.array(z.string().trim().refine((u) => u.includes("://"), "Enter a notification URL like scheme://...")),
  }),
});

/** Masked by default; admins may reveal. Never rendered into toasts. */
function UrlRow({ index, value, error, onChange, onRemove }: { index: number; value: string; error?: string; onChange: (v: string) => void; onRemove: () => void }) {
  const [show, setShow] = useState(false);
  return (
    <div className="grid gap-1">
      <div className="flex items-center gap-2">
        <input
          type={show ? "text" : "password"}
          autoComplete="off"
          spellCheck={false}
          aria-label={`Notification URL ${index + 1}`}
          aria-invalid={error ? true : undefined}
          value={value}
          onChange={(ev) => onChange(ev.target.value)}
          className={`${inputClass} font-mono`}
        />
        <button
          type="button"
          aria-label={show ? "Hide value" : "Show value"}
          aria-pressed={show}
          onClick={() => setShow((s) => !s)}
          className="inline-flex size-9 shrink-0 items-center justify-center rounded-md hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
        >
          {show ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
        </button>
        <button
          type="button"
          aria-label={`Remove URL ${index + 1}`}
          onClick={onRemove}
          className="inline-flex size-9 shrink-0 items-center justify-center rounded-md hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
        >
          <Trash2 className="size-4" aria-hidden />
        </button>
      </div>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    </div>
  );
}

export function NotifySettingsForm({ value }: { value?: SettingsDoc["notify"] }) {
  const save = useSaveSettings();
  const form = useApiForm(schema, {
    defaultValues: { notify: { on: value?.on ?? ["failure"], urls: value?.urls ?? [] } },
    onSubmit: async (v) => {
      await save.mutateAsync({ notify: v.notify });
      toast.success("Notification settings saved");
    },
  });
  const e = form.formState.errors.notify;
  const urlErrors = e?.urls as ({ message?: string } | undefined)[] | undefined;
  return (
    <form onSubmit={form.submit} className="grid gap-4" noValidate>
      <Controller
        control={form.control}
        name="notify.on"
        render={({ field }) => (
          <fieldset className="grid gap-1.5">
            <legend className="text-sm font-medium">Notify on</legend>
            {EVENTS.map(([k, label]) => (
              <label key={k} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={field.value.includes(k)}
                  onChange={(ev) => field.onChange(ev.target.checked ? [...field.value, k] : field.value.filter((x) => x !== k))}
                />
                {label}
              </label>
            ))}
          </fieldset>
        )}
      />
      <Controller
        control={form.control}
        name="notify.urls"
        render={({ field }) => (
          <fieldset className="grid gap-2">
            <legend className="text-sm font-medium">Notification URLs</legend>
            <p className="text-xs text-muted-foreground">Apprise URLs. Masked by default; saving sends the full list.</p>
            {field.value.map((u, i) => (
              <UrlRow
                key={i}
                index={i}
                value={u}
                error={urlErrors?.[i]?.message}
                onChange={(nv) => field.onChange(field.value.map((x, j) => (j === i ? nv : x)))}
                onRemove={() => field.onChange(field.value.filter((_, j) => j !== i))}
              />
            ))}
            <div>
              <button
                type="button"
                onClick={() => field.onChange([...field.value, ""])}
                className="inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
              >
                <Plus className="size-4" aria-hidden /> Add URL
              </button>
            </div>
          </fieldset>
        )}
      />
      <SaveBar root={form.rootError} busy={form.formState.isSubmitting} />
    </form>
  );
}
