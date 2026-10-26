/** Drop listed keys whose value is undefined or blank, so a PATCH never sends an empty secret/api_key. */
export function omitEmpty<T extends object, K extends keyof T>(values: T, keys: readonly K[]): Omit<T, K> & Partial<Pick<T, K>> {
  const out: Record<string, unknown> = { ...(values as Record<string, unknown>) };
  for (const k of keys) {
    const v = out[k as string];
    if (v === undefined || v === null || (typeof v === "string" && v.trim() === "")) delete out[k as string];
  }
  return out as Omit<T, K> & Partial<Pick<T, K>>;
}
