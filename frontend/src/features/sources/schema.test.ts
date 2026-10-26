import { describe, expect, it } from "vitest";
import { defaultValues, emptyFilters, sourceSchema, summarize } from "./schema";

const valid = { ...defaultValues(), name: "n", url: "https://x.y/z", target_id: "3" };
const withFilters = (f: object) => sourceSchema.safeParse({ ...valid, filters: { ...emptyFilters(), ...f } });
const msgs = (r: ReturnType<typeof withFilters>) => (r.success ? [] : r.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`));

describe("sourceSchema filters", () => {
  it("requires integers for width, height, bytes", () => {
    expect(withFilters({ min_width: 1.5 }).success).toBe(false);
    expect(withFilters({ min_height: 2.5 }).success).toBe(false);
    expect(withFilters({ max_bytes: 1.5 }).success).toBe(false);
  });
  it("max_items >= 1", () => {
    expect(withFilters({ max_items: 0 }).success).toBe(false);
    expect(withFilters({ max_items: 1 }).success).toBe(true);
  });
  it("lo <= hi for bytes, aspect, dates", () => {
    expect(withFilters({ min_bytes: 10, max_bytes: 5 }).success).toBe(false);
    expect(withFilters({ aspect_min: 2, aspect_max: 1 }).success).toBe(false);
    expect(msgs(withFilters({ date_from: "2024-02-01", date_to: "2024-01-01" })).join()).toContain("filters.date_to");
    expect(withFilters({ min_bytes: 5, max_bytes: 5, aspect_min: 1, aspect_max: 1 }).success).toBe(true);
  });
  it("summary formats bytes as KB/MB", () => {
    expect(summarize({ ...emptyFilters(), min_bytes: 2048, max_bytes: 3 * 1024 * 1024 })).toContain("size ≥ 2 KB, size ≤ 3 MB");
  });
});
