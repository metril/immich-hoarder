import { describe, expect, it } from "vitest";
import { formatRelative } from "./formatRelative";

describe("formatRelative", () => {
  it("treats Z-suffixed ISO as UTC", () => {
    const now = Date.parse("2026-01-01T12:00:00Z");
    expect(formatRelative("2026-01-01T12:00:00Z", now)).toBe("now");
    expect(formatRelative("2026-01-01T08:00:00Z", now)).toBe("4 hours ago");
  });
});
