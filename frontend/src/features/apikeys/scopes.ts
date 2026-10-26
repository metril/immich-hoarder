/** Mirrors backend/app/auth/principal.py SCOPES (not enumerated in openapi), in order. */
export const SCOPES = [
  "sources:read",
  "sources:write",
  "sources:run",
  "targets:read",
  "targets:write",
  "credentials:read",
  "credentials:write",
  "jobs:read",
  "jobs:write",
  "keys:read",
  "keys:write",
  "metrics:read",
  "admin",
] as const;
export type Scope = (typeof SCOPES)[number];

export const readOnlyScopes = (): string[] => SCOPES.filter((s) => s.endsWith(":read"));
export const allScopes = (admin: boolean): string[] => SCOPES.filter((s) => admin || s !== "admin");

/** Scopes grouped by resource (the part before ":"); `admin` is its own group. */
export function groupScopes(admin: boolean): [string, string[]][] {
  const groups = new Map<string, string[]>();
  for (const s of allScopes(admin)) {
    const g = s.split(":")[0]!;
    groups.set(g, [...(groups.get(g) ?? []), s]);
  }
  return [...groups];
}
