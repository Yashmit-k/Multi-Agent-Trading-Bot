import { createRequire } from "module";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const require = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "../../..");
const schemaDir = path.join(repoRoot, "docs/contracts/schemas");
const outDir = path.join(__dirname, "../src/contracts/generated");

fs.mkdirSync(outDir, { recursive: true });
for (const file of fs.readdirSync(schemaDir)) {
  if (file.endsWith(".json")) {
    fs.copyFileSync(path.join(schemaDir, file), path.join(outDir, file));
  }
}

const catalog = JSON.parse(fs.readFileSync(path.join(outDir, "ContractCatalog.json"), "utf8"));
const envelope = JSON.parse(fs.readFileSync(path.join(outDir, "EventEnvelope.json"), "utf8"));
const mapping = envelope.discriminator?.mapping ?? {};
const eventTypes = Object.keys(mapping);

const vocab = `/* generated — do not edit */
export const SCHEMA_VERSION = "1.0" as const;
export const EVENT_TYPES = ${JSON.stringify(eventTypes, null, 2)} as const;
export type EventType = (typeof EVENT_TYPES)[number];
export const STREAM_EVENT_TYPES = [
  "market.tick",
  "market.candle",
  "feature.updated",
  "agent.signal",
  "news.article",
  "news.signal",
  "decision.created",
  "risk.approved",
  "risk.rejected",
  "order.updated",
  "order.filled",
  "position.updated",
  "portfolio.updated",
  "system.alert",
] as const;
export const TRADING_MODES = ["BACKTEST", "PAPER", "SHADOW", "LIVE"] as const;
export type TradingMode = (typeof TRADING_MODES)[number];
export const HORIZONS = ["INTRADAY", "SWING", "LONG_TERM"] as const;
export const FUNDAMENTAL_AGENTS = ["fundamental", "valuation", "earnings"] as const;
export const DISCRIMINATOR_MAPPING = ${JSON.stringify(mapping, null, 2)} as const;
`;

fs.writeFileSync(path.join(outDir, "vocab.ts"), vocab);
console.log("wrote", outDir);
