import { useMemo } from "react";
import { Controller } from "react-hook-form";
import { FormField, FormRootError, inputClass } from "../../components/common/FormField";
import { useApiForm } from "../../components/common/useApiForm";
import { useCredentials } from "../credentials/hooks";
import { useTargets } from "../targets/hooks";
import { AlbumTemplateField } from "./AlbumTemplateField";
import { BackfillField } from "./BackfillField";
import { CronField } from "./CronField";
import { ExtractorHint } from "./ExtractorHint";
import { FilterBuilder } from "./FilterBuilder";
import { NotifyField } from "./NotifyField";
import { useCreateSource, useUpdateSource, type FilterSpec, type SourceOut, type SourcePatch } from "./hooks";
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

const btn = "rounded-md border px-3 py-1.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring";

export function SourceForm({ initial, onSaved, onCancel }: { initial?: SourceOut; onSaved: (s: SourceOut) => void; onCancel?: () => void }) {
  const create = useCreateSource();
  const update = useUpdateSource(initial?.id ?? 0);
  const targets = useTargets().rows;
  const credentials = useCredentials().rows;
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

  return (
    <form onSubmit={form.submit} className="grid gap-4" noValidate aria-label={initial ? `Edit ${initial.name}` : "New source"}>
      <FormField label="Name" error={e.name?.message}>
        <input className={inputClass} {...form.register("name")} />
      </FormField>
      <div className="grid gap-1">
        <FormField label="URL" error={e.url?.message}>
          <input className={inputClass} inputMode="url" {...form.register("url")} />
        </FormField>
        <ExtractorHint url={url} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label="Target" error={e.target_id?.message}>
          <select className={inputClass} {...form.register("target_id")}>
            <option value="">Select a target…</option>
            {targets.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </FormField>
        <FormField label="Credential" error={e.credential_id?.message}>
          <select className={inputClass} {...form.register("credential_id")}>
            <option value="">None</option>
            {credentials.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </FormField>
      </div>
      <Controller control={form.control} name="album_template" render={({ field }) => (
        <AlbumTemplateField value={field.value} onChange={field.onChange} error={e.album_template?.message} />
      )} />
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
      <Controller control={form.control} name="filters" render={({ field }) => (
        <FilterBuilder value={field.value} onChange={field.onChange} errors={filterErrors} />
      )} />
      <Controller control={form.control} name="notify" render={({ field }) => (
        <NotifyField value={field.value} onChange={field.onChange} error={(e.notify)?.message} />
      )} />
      <details className="rounded-md border p-3">
        <summary className="cursor-pointer text-sm font-medium">Advanced</summary>
        <div className="mt-3 grid gap-4">
          <FormField label="gallery-dl options (JSON)" error={e.gdl_options?.message} hint="Allow-listed options only; the server validates.">
            <textarea className={`${inputClass} h-28 py-2 font-mono`} spellCheck={false} {...form.register("gdl_options")} />
          </FormField>
          <FormField label="Proxy" error={e.proxy?.message}>
            <input className={inputClass} placeholder="socks5h://host:1080" {...form.register("proxy")} />
          </FormField>
          <FormField label="Log level" error={e.log_level?.message}>
            <select className={inputClass} {...form.register("log_level")}>
              <option value="">Default</option>
              {LOG_LEVELS.map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </FormField>
        </div>
      </details>
      {!initial && (
        <FormField label="Visibility" error={e.visibility?.message} hint="Change later via Share.">
          <select className={inputClass} {...form.register("visibility")}>
            <option value="private">Private</option>
            <option value="everyone">Everyone</option>
            <option value="restricted">Restricted</option>
          </select>
        </FormField>
      )}
      <div className="flex flex-wrap gap-4">
        {(["enabled", "allow_animated", "ephemeral"] as const).map((k) => (
          <label key={k} className="flex items-center gap-1.5 text-sm">
            <input type="checkbox" {...form.register(k)} />
            {k === "enabled" ? "Enabled" : k === "allow_animated" ? "Allow animated" : "Ephemeral"}
          </label>
        ))}
      </div>
      <FormRootError message={form.rootError} />
      <div className="flex justify-end gap-2">
        {onCancel && (
          <button type="button" className={btn} onClick={onCancel}>Cancel</button>
        )}
        <button type="submit" disabled={form.formState.isSubmitting} className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50">
          Save
        </button>
      </div>
    </form>
  );
}
