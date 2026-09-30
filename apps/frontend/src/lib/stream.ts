import Ajv, { type ValidateFunction } from "ajv";
import addFormats from "ajv-formats";
import envelopeSchema from "../contracts/generated/EventEnvelope.json";
import { EVENT_TYPES, SCHEMA_VERSION, STREAM_EVENT_TYPES, type EventType } from "../contracts/generated/vocab";

const STREAM = new Set<string>(STREAM_EVENT_TYPES);

export type StreamResult =
  | { ok: true; event: Record<string, unknown> }
  | { ok: false; reason: string; provisional?: boolean };

function compileEnvelope(): ValidateFunction | null {
  const ajv = new Ajv({ allErrors: true, strict: false, discriminator: true });
  addFormats(ajv);
  try {
    return ajv.compile(envelopeSchema as object);
  } catch {
    return null;
  }
}

export const envelopeValidate = compileEnvelope();
export const envelopeCompileOk = envelopeValidate !== null;

const mapping: Record<string, string> =
  (envelopeSchema as { discriminator?: { mapping?: Record<string, string> } }).discriminator?.mapping ?? {};

export function allowlistedEventTypesMatchUnion(): boolean {
  const mapped = new Set(Object.keys(mapping));
  return EVENT_TYPES.every((item) => mapped.has(item));
}

class LruSet {
  private readonly map = new Map<string, true>();
  constructor(private readonly max: number) {}
  has(key: string): boolean {
    return this.map.has(key);
  }
  add(key: string): void {
    if (this.map.has(key)) {
      this.map.delete(key);
    }
    this.map.set(key, true);
    if (this.map.size > this.max) {
      const first = this.map.keys().next().value as string | undefined;
      if (first !== undefined) this.map.delete(first);
    }
  }
  clear(): void {
    this.map.clear();
  }
}

const seen = new LruSet(5000);

export function resetDedupeForTests(): void {
  seen.clear();
}

export function ingestStreamMessage(raw: string): StreamResult {
  let parsed: Record<string, unknown>;
  try {
    parsed = JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return { ok: false, reason: "invalid_json" };
  }
  for (const field of ["event_id", "event_type", "timestamp", "source", "correlation_id"] as const) {
    if (typeof parsed[field] !== "string" || !parsed[field]) {
      return { ok: false, reason: "envelope_shape" };
    }
  }
  const eventType = parsed.event_type as string;
  if (!STREAM.has(eventType)) {
    return { ok: false, reason: "event_type" };
  }
  if (parsed.schema_version !== SCHEMA_VERSION) {
    return { ok: false, reason: "schema_version" };
  }
  const id = parsed.event_id as string;
  if (seen.has(id)) {
    return { ok: false, reason: "duplicate" };
  }
  if (!mapping[eventType]) {
    return { ok: true, event: { ...parsed, provisional: true } };
  }
  if (envelopeValidate) {
    if (!envelopeValidate(parsed)) {
      return { ok: false, reason: "payload" };
    }
  }
  seen.add(id);
  return { ok: true, event: parsed };
}

export function createStream(url: string, onEvent: (event: Record<string, unknown>) => void): () => void {
  let stopped = false;
  let delay = 500;
  let socket: WebSocket | null = null;

  const connect = () => {
    if (stopped) return;
    socket = new WebSocket(url);
    socket.onmessage = (ev) => {
      const result = ingestStreamMessage(String(ev.data));
      if (result.ok) onEvent(result.event);
      else console.warn("ws_drop", result.reason);
    };
    socket.onopen = () => {
      delay = 500;
    };
    socket.onclose = () => {
      if (stopped) return;
      delay = Math.min(delay * 2, 15000);
      setTimeout(connect, delay);
    };
  };
  connect();
  return () => {
    stopped = true;
    socket?.close();
  };
}

export { STREAM as STREAM_ALLOWLIST };
