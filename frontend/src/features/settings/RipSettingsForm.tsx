import { Controller } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { FormField } from "../../components/common/FormField";
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
    <form onSubmit={form.submit} className="grid gap-5" noValidate>
      <FormField label="Upload concurrency" error={e?.upload_concurrency?.message} hint="Files uploaded to Immich in parallel within a single job (1–16). Higher is faster but loads Immich more.">
        <Input type="number" {...form.register("rip.upload_concurrency", { valueAsNumber: true })} />
      </FormField>
      <FormField label="Job scratch max (bytes)" error={e?.job_scratch_max_bytes?.message} hint="Empty = unlimited">
        <Input type="number" {...form.register("rip.job_scratch_max_bytes", num)} />
      </FormField>
      <FormField label="Proxy" error={e?.proxy?.message} hint="e.g. socks5://host:1080. Empty = none">
        <Input spellCheck={false} {...form.register("rip.proxy", str)} />
      </FormField>
      <Controller
        control={form.control}
        name="rip.allow_private_hosts"
        render={({ field }) => (
          <div className="flex items-center gap-3">
            <Switch id="allow-private" checked={field.value} onCheckedChange={field.onChange} />
            <Label htmlFor="allow-private">Allow private hosts</Label>
          </div>
        )}
      />
      <Controller
        control={form.control}
        name="rip.rate_limits"
        render={({ field }) => <RateLimitsEditor value={field.value} onChange={field.onChange} errors={e?.rate_limits} />}
      />
      <SaveBar root={form.rootError} busy={form.formState.isSubmitting} />
    </form>
  );
}
