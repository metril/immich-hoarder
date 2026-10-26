import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { keys } from "../api/keys";
import type { components } from "../api/schema";
import { openStream } from "./sse";
import type { Item, JobEvent, JobStatus, LogLine } from "./types";

type JobOut = components["schemas"]["JobOut"];

export const MAX_LOG = 20_000;
export const MAX_ITEMS = 5_000;
export const FLUSH_MS = 100;

export interface JobStreamState {
  log: LogLine[];
  items: Item[];
  counters: Record<string, number>;
  rate: number | undefined;
  phase: string | undefined;
  status: JobStatus | undefined;
  truncated: boolean;
  connected: boolean;
}

const EMPTY: JobStreamState = {
  log: [],
  items: [],
  counters: {},
  rate: undefined,
  phase: undefined,
  status: undefined,
  truncated: false,
  connected: false,
};

export function useJobStream(jobId: number): JobStreamState {
  const qc = useQueryClient();
  const [snap, setSnap] = useState<{ jobId: number; s: JobStreamState }>({ jobId, s: EMPTY });

  useEffect(() => {
    let log: LogLine[] = [];
    let items: Item[] = [];
    const seen = new Set<string>();
    let counters: Record<string, number> = {};
    let rate: number | undefined;
    let phase: string | undefined;
    let status: JobStatus | undefined;
    let truncated = false;
    let connected = false;
    let dirty = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const trim = <T extends { id: number }>(arr: T[], max: number, prefix: string): T[] => {
      if (arr.length <= max) return arr;
      for (const d of arr.slice(0, arr.length - max)) seen.delete(`${prefix}:${d.id}`);
      truncated = true;
      return arr.slice(arr.length - max);
    };

    const flush = () => {
      timer = undefined;
      if (!dirty) return;
      dirty = false;
      log = trim(log, MAX_LOG, "e");
      items = trim(items, MAX_ITEMS, "i");
      setSnap({
        jobId,
        s: { log: [...log], items: [...items], counters, rate, phase, status, truncated, connected },
      });
      qc.setQueryData<JobOut>(keys.detail("jobs", jobId), (old) =>
        old
          ? {
              ...old,
              ...(status ? { status } : {}),
              ...(phase !== undefined ? { phase } : {}),
              counters: { ...old.counters, ...counters },
            }
          : old,
      );
    };
    const schedule = () => {
      dirty = true;
      timer ??= setTimeout(flush, FLUSH_MS);
    };

    const onEvent = (ev: JobEvent) => {
      switch (ev.type) {
        case "log":
        case "phase": {
          const k = `e:${ev.id}`;
          if (seen.has(k)) return;
          seen.add(k);
          if (ev.type === "log") log.push(ev);
          else phase = ev.name;
          break;
        }
        case "progress":
          counters = { ...counters, ...ev.counters };
          if (ev.rate_bps !== undefined) rate = ev.rate_bps;
          break;
        case "status":
          status = ev.status;
          break;
        case "gap":
          for (const key of [keys.detail("jobs", jobId), keys.jobItems(jobId), keys.jobEvents(jobId)]) {
            void qc.invalidateQueries({ queryKey: key.slice(0, key[0] === "detail" ? 3 : 2) });
          }
          return;
        default: {
          const k = `i:${ev.id}`;
          if (seen.has(k)) return;
          seen.add(k);
          items.push(ev);
        }
      }
      schedule();
    };

    const close = openStream(`/api/v1/jobs/${jobId}/stream`, onEvent, {
      onOpen: () => {
        connected = true;
        schedule();
      },
      onError: () => {
        connected = false;
        schedule();
      },
      onEnd: () => {
        connected = false;
        schedule();
      },
    });
    return () => {
      close();
      clearTimeout(timer);
    };
  }, [jobId, qc]);

  return snap.jobId === jobId ? snap.s : EMPTY;
}
