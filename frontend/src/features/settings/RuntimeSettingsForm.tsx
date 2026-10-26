import { Controller } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { FormField, inputClass } from "../../components/common/FormField";
import { useApiForm } from "../../components/common/useApiForm";
import { CronField } from "../sources/CronField";
import { SaveBar } from "./fields";
import { num } from "./setValue";
import { useSaveSettings, type SettingsDoc } from "./hooks";

const nullableInt = (min: number, max: number) => z.number().int().min(min, `Min ${min}`).max(max, `Max ${max}`).nullable();
const schema = z.object({
  runtime: z.object({
    retention_days: z.number("Required").int().min(1, "Min 1").max(3650, "Max 3650"),
    backup_cron: z.string().trim().min(1, "Required"),
    backup_keep: z.number("Required").int().min(0, "Min 0").max(365, "Max 365"),
    max_concurrent_jobs: nullableInt(1, 64),
    cancel_grace_s: z.number("Required").int().min(0, "Min 0").max(300, "Max 300"),
  }),
});

export function RuntimeSettingsForm({ value }: { value?: SettingsDoc["runtime"] }) {
  const save = useSaveSettings();
  const form = useApiForm(schema, {
    defaultValues: {
      runtime: {
        retention_days: value?.retention_days ?? 30,
        backup_cron: value?.backup_cron ?? "0 3 * * *",
        backup_keep: value?.backup_keep ?? 7,
        max_concurrent_jobs: value?.max_concurrent_jobs ?? null,
        cancel_grace_s: value?.cancel_grace_s ?? 10,
      },
    },
    onSubmit: async (v) => {
      await save.mutateAsync({ runtime: v.runtime });
      toast.success("Runtime settings saved");
    },
  });
  const e = form.formState.errors.runtime;
  return (
    <form onSubmit={form.submit} className="grid gap-3" noValidate>
      <FormField label="Retention (days)" error={e?.retention_days?.message} hint="Finished jobs older than this are pruned">
        <input type="number" className={inputClass} {...form.register("runtime.retention_days", { valueAsNumber: true })} />
      </FormField>
      <Controller
        control={form.control}
        name="runtime.backup_cron"
        render={({ field }) => (
          <CronField value={field.value} onChange={(v) => field.onChange(v ?? "")} error={e?.backup_cron?.message} />
        )}
      />
      <FormField label="Backups to keep" error={e?.backup_keep?.message} hint="0 keeps none">
        <input type="number" className={inputClass} {...form.register("runtime.backup_keep", { valueAsNumber: true })} />
      </FormField>
      <FormField label="Max concurrent jobs" error={e?.max_concurrent_jobs?.message} hint="Empty = server default">
        <input type="number" className={inputClass} {...form.register("runtime.max_concurrent_jobs", num)} />
      </FormField>
      <FormField label="Cancel grace (seconds)" error={e?.cancel_grace_s?.message}>
        <input type="number" className={inputClass} {...form.register("runtime.cancel_grace_s", { valueAsNumber: true })} />
      </FormField>
      <SaveBar root={form.rootError} busy={form.formState.isSubmitting} />
    </form>
  );
}
