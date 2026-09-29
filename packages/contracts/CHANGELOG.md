# Changelog

## 1.0.0 - 2026-09-29

Initial contract release for the multi-agent Indian equities system.

- Pydantic models for signals, news, fundamentals, features, proposals, risk decisions, orders, executions, positions, portfolios, and the Redis event envelope.
- Canonical agent ids, horizons, trading modes, order states, event types, and Redis channels.
- Provider and agent protocols, plus deterministic fakes for RELIANCE, TCS, INFY, HDFCBANK, and ICICIBANK.
- Reference routes `POST /api/v1/internal/signals` and `GET /api/v1/system/contracts`.
- Generated JSON Schema and OpenAPI under `docs/contracts`.
