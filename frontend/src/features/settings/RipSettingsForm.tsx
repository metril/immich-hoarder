import { Controller } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { FormField, inputClass } from "../../components/common/FormField";
import { useApiForm } from "../../components/common/useApiForm";
import { SaveBar } from "./fields";
import { num, str } from "./setValue";
import { useSaveSettings, type SettingsDoc } from "./hooks";
import { RateLimitsEditor } from "./RateLimitsEditor";

const rl = z.object({ sleep_request: z.number("Required").min(0, "Min 0"), sleep: z.number("Required").min(0, "Min 0"), retries: z.number("Required").int().min(0, "Min 0") });
const schema = z.object({
  rip: z.object({
    upload_concurrency: z.number("Required").int().min(1, "Min 1").max(16, "Max 16"),
    allow_private_hosts: z.boolean(),
    job_scratch_max_bytes: z.number().int().min(1, "Min 1").nullable(),
    proxy: z.string().nullable(),
    rate_limits: z.record(z.string(), rl),
  }),
});

export function RipSettingsForm({ value }: { value?: SettingsDoc["rip"] }) {
  const save = useSaveSettings();
  const form = useApiForm(schema, {
    defaultValues: {
      rip: {
        upload_concurrency: value?.upload_concurrency ?? 4,
        allow_private_hosts: value?.allow_private_hosts ?? false,
        job_scratch_max_bytes: value?.job_scratch_max_bytes ?? null,
        proxy: value?.proxy ?? null,
        rate_limits: value?.rate_limits ?? {},
      },
    },
    onSubmit: async (v) => {
      await save.mutateAsync({ rip: v.rip });
      toast.success("Rip settings saved");
    },
  });
  const e = form.formState.errors.rip;
  return (
    <form onSubmit={form.submit} className="grid gap-3" noValidate>
      <FormField label="Upload concurrency" error={e?.upload_concurrency?.message}>
        <input type="number" className={inputClass} {...form.register("rip.upload_concurrency", { valueAsNumber: true })} />
      </FormField>
      <FormField label="Job scratch max (bytes)" error={e?.job_scratch_max_bytes?.message} hint="Empty = unlimited">
        <input type="number" className={inputClass} {...form.register("rip.job_scratch_max_bytes", num)} />
      </FormField>
      <FormField label="Proxy" error={e?.proxy?.message} hint="e.g. socks5://host:1080. Empty = none">
        <input className={inputClass} spellCheck={false} {...form.register("rip.proxy", str)} />
      </FormField>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" {...form.register("rip.allow_private_hosts")} />
        Allow private hosts
      </label>
      <Controller
        control={form.control}
        name="rip.rate_limits"
        render={({ field }) => <RateLimitsEditor value={field.value} onChange={field.onChange} errors={e?.rate_limits} />}
      />
      <SaveBar root={form.rootError} busy={form.formState.isSubmitting} />
    </form>
  );
}
