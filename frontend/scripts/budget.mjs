import { readFileSync } from "node:fs";
import { join } from "node:path";
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
    for (const key of chunk.imports ?? []) visit(manifest[key]);
  };
  visit(entry);
  const sizes = files.map((f) => gzipSync(readFile(f), { level: 9 }).length);
  return { files, sizes, gzipBytes: sizes.reduce((a, b) => a + b, 0) };
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
  return 0;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const [dir, max] = process.argv.slice(2);
  if (!dir || !max) {
    console.error("usage: budget.mjs <dir> <maxBytes>");
    process.exit(2);
  }
  const manifest = JSON.parse(readFileSync(join(dir, ".vite/manifest.json"), "utf8"));
  process.exit(runBudget(manifest, (f) => readFileSync(join(dir, f)), Number(max)));
}
