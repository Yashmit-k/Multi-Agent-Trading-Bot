# Core and contracts requests (from Developer 2 / quant + frontend)

## SignalSink
Core owns the implementation. Quant injects `SignalSink` into the runner. Please provide retries, timeouts, and idempotent handling of duplicate `signal_id`.

## Internal signals HTTP
Please confirm `POST /api/v1/internal/signals` and headers `X-Trading-Mode` / `X-Replay-As-Of`, or open a contracts PR.

## Feature read API
Agents currently use fixture `FeatureProvider`s. Please expose a point-in-time feature-read endpoint.

## system.alert from agents
`SignalSink` only carries `AgentSignal`. In live modes agents need a Core-owned channel to emit `system.alert`.

## timestamp vs as_of
Please define these fields in contracts. Quant treats `as_of` as the knowledge cutoff and `timestamp` as production time from an injected clock.

## EventEnvelope JSON export
Python-only rules (`risk.approved` requires APPROVED, etc.) are not in `EventEnvelope.json`. Please export them (for example `const` status on variants).

If Ajv cannot compile the union with `discriminator: true`, please export an Ajv-compatible discriminator (`propertyName` plus `const` on each `oneOf` variant) without relying on OpenAPI `mapping` alone.

## Market calendar
Please own a shared NSE calendar in Core or a shared utility (not the contracts package). Needs special sessions (Muhurat) and history before 2024. Quant ships a temporary `StaticNseCalendar` for 2024–2026 only.
