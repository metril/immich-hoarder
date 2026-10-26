import type { LogLine } from "../../live/types";

export const LEVELS = ["trace", "debug", "info", "warn", "error"] as const;
export type Level = (typeof LEVELS)[number];

const rank = (l: string): number => LEVELS.indexOf(l as Level);

export function filterLog(lines: LogLine[], { minLevel, query }: { minLevel: Level; query: string }): LogLine[] {
  const min = rank(minLevel);
  const q = query.trim().toLowerCase();
  return lines.filter(
    (l) =>
      rank(l.level) >= min &&
      (q === "" || l.msg.toLowerCase().includes(q) || (l.logger ?? "").toLowerCase().includes(q)),
  );
}
