import { TRADING_MODES, type TradingMode } from "@/contracts/generated/vocab";

export function parseMode(raw: string | undefined): TradingMode | "UNKNOWN" {
  if (raw && (TRADING_MODES as readonly string[]).includes(raw)) return raw as TradingMode;
  return "UNKNOWN";
}
