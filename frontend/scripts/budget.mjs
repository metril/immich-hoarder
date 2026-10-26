import { readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { gzipSync } from "node:zlib";

/** Entry chunk + static imports (never dynamicImports), gzip level 9. */
export function computeInitialJs(manifest, readFile) {
  const entry = Object.values(manifest).find((c) => c.isEntry);
  if (!entry) throw new Error("no isEntry chunk in manifest");
  const seen = new Set();
  const files = [];
  const visit = (chunk) => {
    if (seen.has(chunk)) return;
    seen.add(chunk);
    if (chunk.file.endsWith(".js")) files.push(chunk.file);
    for (const key of chunk.imports ?? []) {
      const dep = manifest[key];
      if (!dep) throw new Error(`manifest key not found: ${key}`);
      visit(dep);
    }
  };
  visit(entry);
  const sizes = files.map((f) => gzipSync(readFile(f), { level: 9 }).length);
  return { files, sizes, gzipBytes: sizes.reduce((a, b) => a + b, 0) };
}

/** Lazy-only libraries; a literal that survives minification identifies each. */
export const LAZY_MARKERS = {
  cronstrue: "Expression has only",
  zod: "Too small: expected",
  "react-hook-form": "isSubmitSuccessful",
};

/** Names of marker libraries whose code is in the entry's static import graph (R3). */
export function findEagerMarkers(manifest, readFile, markers = LAZY_MARKERS) {
  const { files } = computeInitialJs(manifest, readFile);
  const text = files.map((f) => readFile(f).toString("utf8")).join("\n");
  return Object.entries(markers).filter(([, m]) => text.includes(m)).map(([n]) => n);
}

/** Returns the process exit code (1 when over budget). */
export function runBudget(manifest, readFile, maxBytes, log = console.log) {
  const r = computeInitialJs(manifest, readFile);
  r.files.forEach((f, i) => log(`${String(r.sizes[i]).padStart(8)}  ${f}`));
  log(`${String(r.gzipBytes).padStart(8)}  TOTAL (max ${maxBytes})`);
  if (r.gzipBytes > maxBytes) {
    log("FAIL: initial JS over budget");
    return 1;
  }
  const eager = findEagerMarkers(manifest, readFile);
  if (eager.length) {
    log(`FAIL: lazy-only libraries in the initial bundle: ${eager.join(", ")}`);
    return 1;
  }
  return 0;
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [dir, max] = process.argv.slice(2);
  if (!dir || !max) {
    console.error("usage: budget.mjs <dir> <maxBytes>");
    process.exit(2);
  }
  const manifest = JSON.parse(readFileSync(join(dir, ".vite/manifest.json"), "utf8"));
  process.exit(runBudget(manifest, (f) => readFileSync(join(dir, f)), Number(max)));
}
