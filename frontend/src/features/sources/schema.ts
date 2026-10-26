import { z } from "zod";
import type { FilterSpec, SourceNotify, SourceOut } from "./hooks";

export const LOG_LEVELS = ["trace", "debug", "info", "warn", "error"] as const;
export const NOTIFY_EVENTS = ["success", "failure", "new_items"] as const;
export const ALBUM_FIELDS = ["subreddit", "author", "user", "site", "category", "source", "date"] as const;

export function validRegex(v: string | null | undefined): boolean {
  if (!v) return true;
  try {
    new RegExp(v);
    return true;
  } catch {
    return false;
  }
}
const regexField = z
  .string()
  .nullable()
  .refine(validRegex, "Invalid regular expression");
const num = z.number().nullable();

const filters = z.object({
  min_width: num,
  min_height: num,
  min_bytes: num,
  max_bytes: num,
  aspect_min: num,
  aspect_max: num,
  title_include: regexField,
  title_exclude: regexField,
  date_from: z.string().nullable(),
  date_to: z.string().nullable(),
  max_items: num,
  phash_distance: z.number().int().min(0).max(3).nullable(),
});

const notify = z.object({
  credential_ids: z.array(z.number()),
  on: z.array(z.enum(NOTIFY_EVENTS)),
});

const isoDate = (v: string) => /^\d{4}-\d{2}-\d{2}$/.test(v) && !Number.isNaN(Date.parse(v));

/** Form schema mirroring SourceIn. Selects/inputs hold strings; the output is the API shape. */
export const sourceSchema = z
  .object({
    name: z.string().trim().min(1, "Name is required").max(255),
    url: z.string().trim().min(1, "URL is required").max(2048),
    target_id: z.string().min(1, "Select a target").transform(Number),
    credential_id: z.string().transform((s) => (s === "" ? null : Number(s))),
    album_template: z.string(),
    schedule_cron: z.string().nullable().transform((v) => v?.trim() || null),
    backfill_mode: z.enum(["full", "last_n", "since"]),
    backfill_value: z.string(),
    allow_animated: z.boolean(),
    filters,
    notify,
    gdl_options: z.string().transform((s, ctx) => {
      let parsed: unknown;
      try {
        parsed = s.trim() === "" ? {} : JSON.parse(s);
      } catch {
        ctx.issues.push({ code: "custom", message: "Must be valid JSON", input: s });
        return z.NEVER;
      }
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        ctx.issues.push({ code: "custom", message: "Must be a JSON object", input: s });
        return z.NEVER;
      }
      return parsed as Record<string, unknown>;
    }),
    proxy: z
      .string()
      .trim()
      .refine((v) => v === "" || /^(https?|socks5h?):\/\//.test(v), "Must start with http://, https://, socks5:// or socks5h://")
      .transform((v) => v || null),
    log_level: z
      .string()
      .refine((v) => v === "" || (LOG_LEVELS as readonly string[]).includes(v), "Unknown log level")
      .transform((v) => v || null),
    enabled: z.boolean(),
    ephemeral: z.boolean(),
    visibility: z.enum(["private", "everyone", "restricted"]),
  })
  .superRefine((v, ctx) => {
    const val = v.backfill_value.trim();
    if (v.backfill_mode === "last_n" && !(/^\d+$/.test(val) && Number(val) >= 1)) {
      ctx.addIssue({ code: "custom", path: ["backfill_value"], message: "Enter a whole number, 1 or more" });
    } else if (v.backfill_mode === "since" && !isoDate(val)) {
      ctx.addIssue({ code: "custom", path: ["backfill_value"], message: "Enter a date (YYYY-MM-DD)" });
    }
  })
  .transform((v) => ({ ...v, backfill_value: v.backfill_mode === "full" ? null : v.backfill_value.trim() }));

export type SourceFormValues = z.input<typeof sourceSchema>;
export type SourceFormOutput = z.output<typeof sourceSchema>;

export const emptyFilters = (f: Partial<FilterSpec> = {}): z.input<typeof filters> => ({
  min_width: f.min_width ?? null,
  min_height: f.min_height ?? null,
  min_bytes: f.min_bytes ?? null,
  max_bytes: f.max_bytes ?? null,
  aspect_min: f.aspect_min ?? null,
  aspect_max: f.aspect_max ?? null,
  title_include: f.title_include ?? null,
  title_exclude: f.title_exclude ?? null,
  date_from: f.date_from ?? null,
  date_to: f.date_to ?? null,
  max_items: f.max_items ?? null,
  phash_distance: f.phash_distance === undefined ? 3 : f.phash_distance,
});

export const normNotify = (n?: Partial<SourceNotify>): z.input<typeof notify> => ({
  credential_ids: n?.credential_ids ?? [],
  on: n?.on ?? ["failure"],
});

export function defaultValues(s?: SourceOut): SourceFormValues {
  return {
    name: s?.name ?? "",
    url: s?.url ?? "",
    target_id: s ? String(s.target_id) : "",
    credential_id: s?.credential_id != null ? String(s.credential_id) : "",
    album_template: s?.album_template ?? "",
    schedule_cron: s?.schedule_cron ?? null,
    backfill_mode: s?.backfill_mode ?? "full",
    backfill_value: s?.backfill_value ?? "",
    allow_animated: s?.allow_animated ?? false,
    filters: emptyFilters(s?.filters),
    notify: normNotify(s?.notify),
    gdl_options: s && Object.keys(s.gdl_options).length > 0 ? JSON.stringify(s.gdl_options, null, 2) : "",
    proxy: s?.proxy ?? "",
    log_level: s?.log_level ?? "",
    enabled: s?.enabled ?? true,
    ephemeral: s?.ephemeral ?? false,
    visibility: s?.visibility ?? "private",
  };
}

export const CRON_PRESETS: { label: string; value: string | null }[] = [
  { label: "Off", value: null },
  { label: "Hourly", value: "0 * * * *" },
  { label: "Every 6 h", value: "0 */6 * * *" },
  { label: "Daily 03:00", value: "0 3 * * *" },
  { label: "Weekly Sun", value: "0 3 * * 0" },
];

export function summarize(f: Partial<FilterSpec>): string {
  const parts: string[] = [];
  const add = (cond: unknown, text: string) => cond != null && cond !== "" && parts.push(text);
  add(f.min_width, `width ≥ ${f.min_width}`);
  add(f.min_height, `height ≥ ${f.min_height}`);
  add(f.min_bytes, `size ≥ ${f.min_bytes} B`);
  add(f.max_bytes, `size ≤ ${f.max_bytes} B`);
  add(f.aspect_min, `aspect ≥ ${f.aspect_min}`);
  add(f.aspect_max, `aspect ≤ ${f.aspect_max}`);
  add(f.title_include, `title matches /${f.title_include}/`);
  add(f.title_exclude, `title excludes /${f.title_exclude}/`);
  add(f.date_from, `from ${f.date_from}`);
  add(f.date_to, `to ${f.date_to}`);
  add(f.max_items, `max ${f.max_items} items`);
  if (f.phash_distance !== 3) parts.push(`pHash distance ${f.phash_distance ?? "off"}`);
  return parts.length ? `Active rules: ${parts.join(", ")}` : "No filters active";
}

