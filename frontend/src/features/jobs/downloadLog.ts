import { api } from "../../api/client";
import { unwrap } from "../../api/errors";

const PAGE = 200; // backend MAX_LIMIT

export interface DownloadOpts {
  signal?: AbortSignal;
  onProgress?: (lines: number) => void;
}

/** Pages are newest-first; each page is serialized once, reversed, and the page order is reversed at the end. */
export async function downloadLog(jobId: number, minLevel?: string, opts: DownloadOpts = {}): Promise<void> {
  const parts: string[] = [];
  let cursor: string | undefined;
  let n = 0;
  do {
    opts.signal?.throwIfAborted();
    const page = unwrap(
      await api.GET("/api/v1/jobs/{job_id}/events", {
        params: { path: { job_id: jobId }, query: { limit: PAGE, ...(minLevel ? { min_level: minLevel } : {}), ...(cursor ? { cursor } : {}) } },
        signal: opts.signal,
      }),
    );
    if (page.items.length > 0) {
      parts.push(page.items.map((e) => JSON.stringify(e) + "\n").reverse().join(""));
      n += page.items.length;
      opts.onProgress?.(n);
    }
    cursor = page.next_cursor ?? undefined;
  } while (cursor);
  opts.signal?.throwIfAborted();
  const url = URL.createObjectURL(new Blob(parts.reverse(), { type: "application/x-ndjson" }));
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
