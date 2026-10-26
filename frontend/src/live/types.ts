import type { components } from "../api/schema";

export type JobStatus = components["schemas"]["JobStatus"];
export type LogLevel = "trace" | "debug" | "info" | "warn" | "error";

export interface Progress {
  type: "progress";
  job_id?: number;
  counters: Record<string, number>;
  bytes?: number;
  rate_bps?: number;
  scratch_bytes?: number;
  scratch_free_ratio?: number;
  total?: number;
}
export interface Status {
  type: "status";
  job_id: number;
  status: JobStatus;
}
export interface Log {
  type: "log";
  id: number;
  ts: string;
  job_id: number;
  level: LogLevel;
  msg: string;
  logger?: string;
  data?: unknown;
}
export interface Phase {
  type: "phase";
  id: number;
  ts: string;
  job_id: number;
  name: string;
}
export interface Item {
  type: `item.${string}`;
  id: number;
  url: string;
  reason?: string | null;
  immich_asset_id?: string | null;
  duplicate?: boolean;
}
export interface Gap {
  type: "gap";
}
export interface End {
  type: "end";
}

export type JobEvent = Progress | Status | Log | Phase | Item | Gap;
export type LogLine = Log;

export const EVENT_TYPES = [
  "progress",
  "status",
  "log",
  "phase",
  "gap",
  "end",
  "item.discovered",
  "item.downloaded",
  "item.filtered",
  "item.failed",
  "item.uploaded",
  "item.linked",
  "item.deleted_in_immich",
] as const;
