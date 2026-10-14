import fs from "node:fs";
import path from "node:path";

const dir = path.join(process.cwd(), ".next");
if (!fs.existsSync(dir)) process.exit(0);

fs.rmSync(dir, { recursive: true, force: true });
console.error("Removed apps/frontend/.next so production build is not blocked by a leftover Next cache.");
