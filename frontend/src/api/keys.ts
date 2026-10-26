export type Resource = "targets" | "credentials" | "sources" | "jobs" | "api-keys" | "users";

export const keys = {
  me: () => ["me"] as const,
  list: (resource: Resource, params?: object) => ["list", resource, params ?? {}] as const,
  detail: (resource: Resource, id: number | string) => ["detail", resource, id] as const,
  jobItems: (id: number | string, outcome?: string) => ["job-items", id, outcome ?? null] as const,
  jobEvents: (id: number | string, minLevel?: string) => ["job-events", id, minLevel ?? null] as const,
  shares: (resource: Resource, id: number | string) => ["shares", resource, id] as const,
  albums: (targetId: number | string) => ["albums", targetId] as const,
  extractors: () => ["extractors"] as const,
  settings: () => ["settings"] as const,
  backups: () => ["backups"] as const,
  uploads: (params?: object) => ["uploads", params ?? {}] as const,
  directory: (q: string) => ["directory", q] as const,
};
