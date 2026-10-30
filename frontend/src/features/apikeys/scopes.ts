import type { components } from "../../api/schema";

/** Derived from the generated ApiKeyIn type (backend Scope literal). */
export type Scope = components["schemas"]["ApiKeyIn"]["scopes"][number];

const ORDER = [
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
  "settings:read",
  "settings:write",
  "users:read",
  "users:write",
  "admin",
] as const satisfies readonly Scope[];

// Compile error if the backend adds a scope missing from ORDER.
type Missing = Exclude<Scope, (typeof ORDER)[number]>;
const _exhaustive: [Missing] extends [never] ? true : never = true;
void _exhaustive;

/** Scopes only admins may hold or grant (mirrors backend ADMIN_ONLY_SCOPES). */
export const ADMIN_ONLY: readonly Scope[] = [
  "settings:read",
  "settings:write",
  "users:read",
  "users:write",
  "admin",
];

export const SCOPES: readonly Scope[] = ORDER;

export const readOnlyScopes = (): Scope[] => SCOPES.filter((s) => s.endsWith(":read"));
export const allScopes = (admin: boolean): Scope[] => SCOPES.filter((s) => admin || !ADMIN_ONLY.includes(s));

/** Scopes grouped by resource (the part before ":"); `admin` is its own group. */
export function groupScopes(admin: boolean): [string, Scope[]][] {
  const groups = new Map<string, Scope[]>();
  for (const s of allScopes(admin)) {
    const g = s.split(":")[0]!;
    groups.set(g, [...(groups.get(g) ?? []), s]);
  }
  return [...groups];
}
