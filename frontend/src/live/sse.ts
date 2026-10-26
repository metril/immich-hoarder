import { api } from "../api/client";
import { EVENT_TYPES, type JobEvent } from "./types";

export const MAX_REJECTED = 5;
export const BACKOFF_MS = [1000, 2000, 5000, 10000] as const;

export interface StreamOpts {
  onEnd?: () => void;
  onOpen?: () => void;
  onError?: () => void;
}

/** Open an SSE stream; returns a disposer. Reconnects with backoff after probing the session. */
export function openStream(url: string, onEvent: (e: JobEvent) => void, opts: StreamOpts = {}): () => void {
  let es: EventSource | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let attempt = 0;
  let stopped = false;
  let rejected = 0;

  const stop = () => {
    stopped = true;
    clearTimeout(timer);
    es?.close();
    es = null;
  };

  const retry = () => {
    const delay = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)];
    attempt += 1;
    timer = setTimeout(async () => {
      try {
        const r = await api.GET("/api/v1/auth/me"); // 401 fires the unauthorized handler
        if (r.response.status === 401) {
          stop();
          return;
        }
      } catch {
        // network blip: keep retrying
      }
      if (!stopped) connect();
    }, delay);
  };

  const connect = () => {
    const src = new EventSource(url);
    es = src;
    src.onopen = () => {
      attempt = 0;
      rejected = 0;
      opts.onOpen?.();
    };
    for (const type of EVENT_TYPES) {
      src.addEventListener(type, (m) => {
        if (stopped || es !== src) return;
        if (type === "end") {
          stop();
          opts.onEnd?.();
          return;
        }
        let data: unknown;
        try {
          data = JSON.parse((m as MessageEvent<string>).data);
        } catch {
          return;
        }
        if (typeof data !== "object" || data === null) return;
        onEvent({ ...data, type } as JobEvent);
      });
    }
    src.addEventListener("error", () => {
      if (stopped || es !== src) return;
      // readyState CLOSED = the server rejected the request (e.g. 429), not a network drop.
      const refused = src.readyState === 2;
      src.close();
      es = null;
      opts.onError?.();
      if (refused && ++rejected >= MAX_REJECTED) {
        stop();
        return;
      }
      retry();
    });
  };

  connect();
  return stop;
}
