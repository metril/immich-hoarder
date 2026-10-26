import { api } from "../../api/client";
import { unwrap } from "../../api/errors";
import type { components } from "../../api/schema";

type EventOut = components["schemas"]["EventOut"];
const PAGE = 200; // backend MAX_LIMIT

export async function fetchAllEvents(jobId: number, minLevel?: string): Promise<EventOut[]> {
  const all: EventOut[] = [];
  let cursor: string | undefined;
  do {
    const page = unwrap(
      await api.GET("/api/v1/jobs/{job_id}/events", {
        params: { path: { job_id: jobId }, query: { limit: PAGE, ...(minLevel ? { min_level: minLevel } : {}), ...(cursor ? { cursor } : {}) } },
      }),
    );
    all.push(...page.items);
    cursor = page.next_cursor ?? undefined;
  } while (cursor);
  return all.sort((a, b) => a.id - b.id);
}

export async function downloadLog(jobId: number, minLevel?: string): Promise<void> {
  const events = await fetchAllEvents(jobId, minLevel);
  const body = events.map((e) => JSON.stringify(e)).join("\n") + (events.length ? "\n" : "");
  const url = URL.createObjectURL(new Blob([body], { type: "application/x-ndjson" }));
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = `job-${jobId}.log.ndjson`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}
