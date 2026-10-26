import { Eye, EyeOff, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Controller } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
        <Input
          type={show ? "text" : "password"}
          autoComplete="off"
          spellCheck={false}
          aria-label={`Notification URL ${index + 1}`}
          aria-invalid={error ? true : undefined}
          value={value}
          onChange={(ev) => onChange(ev.target.value)}
          className="min-w-0 flex-1 font-mono"
        />
        <Button
          variant="ghost"
          size="icon"
          aria-label={show ? "Hide value" : "Show value"}
          aria-pressed={show}
          onClick={() => setShow((s) => !s)}
        >
          {show ? <EyeOff aria-hidden /> : <Eye aria-hidden />}
        </Button>
        <Button variant="ghost" size="icon" aria-label={`Remove URL ${index + 1}`} onClick={onRemove}>
          <Trash2 aria-hidden />
        </Button>
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
    <form onSubmit={form.submit} className="grid gap-6" noValidate>
      <Controller
        control={form.control}
        name="notify.on"
        render={({ field }) => (
          <fieldset className="grid gap-2.5">
            <legend className="text-sm font-medium">Notify on</legend>
            {EVENTS.map(([k, label]) => (
              <label key={k} className="flex items-center gap-2.5 text-sm">
                <input
                  type="checkbox"
                  className="size-4 accent-primary"
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
          <fieldset className="grid gap-3">
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
            {e?.urls?.message && <p role="alert" className="text-sm text-destructive">{e.urls.message}</p>}
            <div>
              <Button variant="outline" size="sm" onClick={() => field.onChange([...field.value, ""])}>
                <Plus aria-hidden /> Add URL
              </Button>
            </div>
          </fieldset>
        )}
      />
      <SaveBar root={form.rootError} busy={form.formState.isSubmitting} />
    </form>
  );
}
