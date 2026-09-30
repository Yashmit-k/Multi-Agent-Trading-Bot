# Provisional mock API models

These types are **not** contracts. They are named `Provisional...` and generated into `apps/frontend/src/api/generated/`.

| Endpoint | Model |
| --- | --- |
| GET /api/v1/system/status | ProvisionalSystemStatus |
| GET /api/v1/market/overview | ProvisionalMarketOverview |
| GET /api/v1/stocks | ProvisionalStock[] |
| GET /api/v1/risk/status | ProvisionalRiskStatus |
| GET /api/v1/performance | ProvisionalPerformance |
| GET /api/v1/stocks/{symbol}/agents | ProvisionalAgentScore[] |

Canonical contract models are used for signals, candles, portfolio, positions, orders, news, and fundamentals.

Unknown `/api/v1/*` routes return 501, matching Core.
