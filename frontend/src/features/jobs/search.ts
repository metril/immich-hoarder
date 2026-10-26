export const JOB_STATUSES = ["queued", "running", "succeeded", "failed", "cancelled"] as const;
export type JobStatusFilter = (typeof JOB_STATUSES)[number];
export interface JobsSearch {
  status?: JobStatusFilter;
  source_id?: number;
}

// Hand-rolled validation: zod must stay out of the eager bundle (ruling R3).
export function validateJobsSearch(s: Record<string, unknown>): JobsSearch {
  const out: JobsSearch = {};
  if (typeof s.status === "string" && (JOB_STATUSES as readonly string[]).includes(s.status)) out.status = s.status as JobStatusFilter;
  const n = typeof s.source_id === "string" ? Number(s.source_id) : s.source_id;
  if (typeof n === "number" && Number.isInteger(n) && n > 0) out.source_id = n;
  return out;
}

