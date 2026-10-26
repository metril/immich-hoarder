import { describe, expect, it } from "vitest";
import { cn } from "@/lib/utils";

describe("cn", () => {
  const off = false as boolean;
  it("merges tailwind classes", () => {
    expect(cn("p-2", "p-4", off && "hidden", "text-sm")).toBe("p-4 text-sm");
  });
});
