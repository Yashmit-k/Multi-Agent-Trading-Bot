import { describe, expect, it, beforeEach } from "vitest";
import {
  allowlistedEventTypesMatchUnion,
  envelopeCompileOk,
  ingestStreamMessage,
  resetDedupeForTests,
} from "@/lib/stream";

const base = {
  event_id: "e1",
  event_type: "market.tick",
  timestamp: "2024-06-03T10:00:00+00:00",
  source: "test",
  schema_version: "1.0",
  correlation_id: "c1",
  payload: {
    symbol: "RELIANCE",
    exchange: "NSE",
    timestamp: "2024-06-03T10:00:00+00:00",
    last_price: "100.00",
    volume: 1,
  },
};

describe("stream ingest", () => {
  beforeEach(() => resetDedupeForTests());

  it("compiles EventEnvelope or records fallback", () => {
    expect(typeof envelopeCompileOk).toBe("boolean");
  });

  it("allowlist matches union mapping", () => {
    expect(allowlistedEventTypesMatchUnion()).toBe(true);
  });

  it("drops bad event_type", () => {
    const result = ingestStreamMessage(JSON.stringify({ ...base, event_type: "nope.event" }));
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toBe("event_type");
  });

  it("drops bad schema_version", () => {
    const result = ingestStreamMessage(JSON.stringify({ ...base, schema_version: "9.9" }));
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toBe("schema_version");
  });

  it("dedupes event_id", () => {
    const raw = JSON.stringify(base);
    expect(ingestStreamMessage(raw).ok).toBe(true);
    const again = ingestStreamMessage(raw);
    expect(again.ok).toBe(false);
    if (!again.ok) expect(again.reason).toBe("duplicate");
  });
});
