import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { brotliCompressSync, constants, gzipSync } from "node:zlib";

const RE = /\.(js|css|html|svg|json|webmanifest|txt)$/;

function* walk(dir) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else yield p;
  }
}

export function compressDir(dir) {
  for (const p of walk(dir)) {
    if (!RE.test(p) || statSync(p).size < 1024) continue;
    const buf = readFileSync(p);
    const br = brotliCompressSync(buf, {
      params: { [constants.BROTLI_PARAM_QUALITY]: 11, [constants.BROTLI_PARAM_SIZE_HINT]: buf.length },
    });
    if (br.length < buf.length) writeFileSync(`${p}.br`, br);
    const gz = gzipSync(buf, { level: 9 });
    if (gz.length < buf.length) writeFileSync(`${p}.gz`, gz);
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const dir = process.argv[2];
  if (!dir) {
    console.error("usage: compress.mjs <dir>");
    process.exit(2);
  }
  compressDir(dir);
}
