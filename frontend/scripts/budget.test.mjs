import { gzipSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import { computeInitialJs, runBudget } from "./budget.mjs";

const manifest = {
  "index.html": { file: "assets/index-a.js", isEntry: true, imports: ["_vendor.js"], dynamicImports: ["src/routes/x.tsx"], css: ["assets/index.css"] },
  "_vendor.js": { file: "assets/vendor-b.js", imports: ["_shared.js"] },
  "_shared.js": { file: "assets/shared-c.js" },
  "src/routes/x.tsx": { file: "assets/x-d.js", isDynamicEntry: true },
};
const files = {
  "assets/index-a.js": "a".repeat(2000),
  "assets/vendor-b.js": "b".repeat(3000),
  "assets/shared-c.js": "c".repeat(1000),
  "assets/x-d.js": "x".repeat(9000),
};
const readFile = (f) => Buffer.from(files[f]);

describe("budget", () => {
  it("counts entry and static imports only", () => {
    const r = computeInitialJs(manifest, readFile);
    expect(r.files.sort()).toEqual(["assets/index-a.js", "assets/shared-c.js", "assets/vendor-b.js"]);
    const expected = ["a".repeat(2000), "b".repeat(3000), "c".repeat(1000)].reduce(
      (n, s) => n + gzipSync(s, { level: 9 }).length, 0);
    expect(r.gzipBytes).toBe(expected);
  });

  it("fails over budget", () => {
    const r = computeInitialJs(manifest, readFile);
    expect(runBudget(manifest, readFile, r.gzipBytes, () => {})).toBe(0);
    expect(runBudget(manifest, readFile, r.gzipBytes - 1, () => {})).toBe(1);
  });

  it("names a missing manifest key", () => {
    const bad = { e: { file: "a.js", isEntry: true, imports: ["nope.js"] } };
    expect(() => computeInitialJs(bad, readFile)).toThrow("nope.js");
  });
});
