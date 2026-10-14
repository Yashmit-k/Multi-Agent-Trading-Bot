import fs from "node:fs";
import path from "node:path";

const dir = path.join(process.cwd(), ".next");
if (!fs.existsSync(dir)) process.exit(0);

function sleep(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function tryRemove() {
  fs.rmSync(dir, { recursive: true, force: true, maxRetries: 12, retryDelay: 150 });
}

function tryRename() {
  const dest = path.join(process.cwd(), `.next.stale-${Date.now()}`);
  fs.renameSync(dir, dest);
  console.error(`Renamed locked apps/frontend/.next to ${path.basename(dest)} so production build can use a fresh cache.`);
}

let lastError;
for (let attempt = 1; attempt <= 6; attempt += 1) {
  try {
    tryRemove();
    console.error("Removed apps/frontend/.next so production build is not blocked by a leftover Next cache.");
    process.exit(0);
  } catch (error) {
    lastError = error;
    try {
      tryRename();
      process.exit(0);
    } catch (renameError) {
      lastError = renameError;
      sleep(250 * attempt);
    }
  }
}

console.error("Could not remove or rename apps/frontend/.next after retries (a next/dev process may be holding files):", lastError);
process.exit(1);
