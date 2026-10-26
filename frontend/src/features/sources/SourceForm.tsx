import { useEffect, useMemo, type ReactNode } from "react";
import { Controller } from "react-hook-form";
import { FormField, FormRootError } from "../../components/common/FormField";
import { useApiForm } from "../../components/common/useApiForm";
import { Button } from "../../components/ui/button";
import { DialogBody, DialogFooter } from "../../components/ui/dialog";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Select } from "../../components/ui/select";
import { Switch } from "../../components/ui/switch";
import { Textarea } from "../../components/ui/textarea";
import { AlbumTemplateField } from "./AlbumTemplateField";
import { BackfillField } from "./BackfillField";
import { CronField } from "./CronField";
import { ExtractorHint } from "./ExtractorHint";
import { FilterBuilder } from "./FilterBuilder";
import { NotifyField } from "./NotifyField";
import { useUsableCredentials, useUsableTargets } from "./pickers";
import { useCreateSource, useUpdateSource, type FilterSpec, type SourceIn, type SourceOut, type SourcePatch } from "./hooks";
import { LOG_LEVELS, defaultValues, sourceSchema, type SourceFormOutput } from "./schema";

const PATCH_KEYS = ["name", "url", "target_id", "credential_id", "album_template", "schedule_cron", "backfill_mode", "backfill_value",
  "allow_animated", "filters", "notify", "gdl_options", "proxy", "log_level", "enabled", "ephemeral"] as const;

/** Only the fields whose value differs from the loaded source. Mode and value travel together. */
function dirtyPatch(next: SourceFormOutput, base: SourceFormOutput): SourcePatch {
  const out: Record<string, unknown> = {};
  for (const k of PATCH_KEYS) {
    if (JSON.stringify(next[k]) !== JSON.stringify(base[k])) out[k] = next[k];
  }
  if ("backfill_mode" in out || "backfill_value" in out) {
    out.backfill_mode = next.backfill_mode;
    out.backfill_value = next.backfill_value;
  }
  return out;
}

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <div className="grid gap-5 rounded-xl border bg-card p-5 text-card-foreground">
      <div className="grid gap-1">
        <h3 className="font-display text-base font-semibold">{title}</h3>
        {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {children}
    </div>
  );
}

const TOGGLES = [
  { key: "enabled", label: "Enabled", hint: "Scheduled runs happen only while enabled." },
  { key: "allow_animated", label: "Allow animated", hint: "Also grab GIFs and videos." },
  { key: "ephemeral", label: "Ephemeral", hint: "Remove the source after it finishes once." },
] as const;

export function SourceForm({ initial, onSaved, onCancel, onDraft, extra }: { initial?: SourceOut; onSaved: (s: SourceOut) => void; onCancel?: () => void; onDraft?: (d: SourceIn | null) => void; extra?: ReactNode }) {
  const create = useCreateSource();
  const update = useUpdateSource(initial?.id ?? 0);
  const targets = useUsableTargets(initial?.target_id);
  const credentials = useUsableCredentials(initial?.credential_id).filter((c) => c.kind !== "apprise");
  const defaults = useMemo(() => defaultValues(initial), [initial]);
  const base = useMemo(() => (initial ? sourceSchema.safeParse(defaults).data : undefined), [initial, defaults]);

  const form = useApiForm(sourceSchema, {
    defaultValues: defaults,
    onSubmit: async (v) => {
      if (initial) {
        const patch = base ? dirtyPatch(v, base) : ({ ...v, visibility: undefined } as SourcePatch);
        onSaved(await update.mutateAsync(patch));
      } else {
        onSaved(await create.mutateAsync(v));
      }
    },
  });
  const e = form.formState.errors;
  const fe = (e.filters ?? {}) as Partial<Record<keyof FilterSpec, { message?: string }>>;
  const filterErrors = Object.fromEntries(Object.entries(fe).map(([k, x]) => [k, x?.message]));
  const url = form.watch("url");
  // Expose the current (parsed) values so the sheet can dry-run an unsaved draft.
  const draftKey = JSON.stringify(form.watch());
  useEffect(() => {
    const r = sourceSchema.safeParse(JSON.parse(draftKey));
    onDraft?.(r.success ? r.data : null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftKey]);

  return (
    <form onSubmit={form.submit} className="flex min-h-0 flex-1 flex-col" noValidate aria-label={initial ? `Edit ${initial.name}` : "New source"}>
      <DialogBody className="grid content-start gap-6 pt-1">
        <Section title="General">
          <FormField label="Name" error={e.name?.message}>
            <Input {...form.register("name")} />
          </FormField>
          <div className="grid gap-2">
            <FormField label="URL" error={e.url?.message}>
              <Input inputMode="url" {...form.register("url")} />
            </FormField>
            <ExtractorHint url={url} />
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            <FormField label="Target" error={e.target_id?.message}>
              <Select {...form.register("target_id")}>
                <option value="">Select a target…</option>
                {targets.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </Select>
            </FormField>
            <FormField label="Credential" error={e.credential_id?.message}>
              <Select {...form.register("credential_id")}>
                <option value="">None</option>
                {credentials.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </Select>
            </FormField>
          </div>
          <Controller control={form.control} name="album_template" render={({ field }) => (
            <AlbumTemplateField value={field.value} onChange={field.onChange} error={e.album_template?.message} />
          )} />
        </Section>
        <Section title="Schedule" description="When and how far back to collect.">
          <Controller control={form.control} name="schedule_cron" render={({ field }) => (
            <CronField value={field.value} onChange={field.onChange} error={e.schedule_cron?.message} />
          )} />
          <Controller control={form.control} name="backfill_mode" render={({ field: mode }) => (
            <Controller control={form.control} name="backfill_value" render={({ field: val }) => (
              <BackfillField
                mode={mode.value}
                value={val.value}
                error={e.backfill_value?.message ?? e.backfill_mode?.message}
                onModeChange={(m) => {
                  mode.onChange(m);
                  val.onChange("");
                }}
                onValueChange={val.onChange}
              />
            )} />
          )} />
        </Section>
        <Section title="Filters" description="Skip items that do not match.">
          <Controller control={form.control} name="filters" render={({ field }) => (
            <FilterBuilder value={field.value} onChange={field.onChange} errors={filterErrors} error={e.filters?.message} />
          )} />
        </Section>
        <Section title="Notifications">
          <Controller control={form.control} name="notify" render={({ field }) => (
            <NotifyField value={field.value} onChange={field.onChange} keep={initial?.notify.credential_ids} error={(e.notify)?.message} />
          )} />
        </Section>
        <Section title="Options">
          <div className="grid gap-4">
            {TOGGLES.map((t) => (
              <div key={t.key} className="flex items-center justify-between gap-4">
                <div className="grid min-w-0 gap-0.5">
                  <Label htmlFor={`src-${t.key}`}>{t.label}</Label>
                  <p className="text-xs text-muted-foreground">{t.hint}</p>
                </div>
                <Controller control={form.control} name={t.key} render={({ field }) => (
                  <Switch id={`src-${t.key}`} checked={field.value} onCheckedChange={field.onChange} />
                )} />
              </div>
            ))}
          </div>
          {!initial && (
            <FormField label="Visibility" error={e.visibility?.message} hint="Change later via Share.">
              <Select {...form.register("visibility")}>
                <option value="private">Private</option>
                <option value="everyone">Everyone</option>
                <option value="restricted">Restricted</option>
              </Select>
            </FormField>
          )}
          <details className="rounded-lg border p-4">
            <summary className="cursor-pointer text-sm font-medium">Advanced</summary>
            <div className="mt-4 grid gap-5">
              <FormField label="gallery-dl options (JSON)" error={e.gdl_options?.message} hint="Allow-listed options only; the server validates.">
                <Textarea className="h-28 font-mono" spellCheck={false} {...form.register("gdl_options")} />
              </FormField>
              <FormField label="Proxy" error={e.proxy?.message}>
                <Input placeholder="socks5h://host:1080" {...form.register("proxy")} />
              </FormField>
              <FormField label="Log level" error={e.log_level?.message}>
                <Select {...form.register("log_level")}>
                  <option value="">Default</option>
                  {LOG_LEVELS.map((l) => (
                    <option key={l} value={l}>{l}</option>
                  ))}
                </Select>
              </FormField>
            </div>
          </details>
        </Section>
        {extra}
        <FormRootError message={form.rootError} />
      </DialogBody>
      <DialogFooter>
        {onCancel && (
          <Button variant="outline" onClick={onCancel}>Cancel</Button>
        )}
        <Button type="submit" loading={form.formState.isSubmitting}>
          Save
        </Button>
      </DialogFooter>
    </form>
  );
}
