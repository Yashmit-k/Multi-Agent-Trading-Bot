# Multi-agent trading

Shared contracts live in [`packages/contracts`](packages/contracts). That package is the only source of truth for schemas, event names, Redis channels, horizons, trading modes, and agent interfaces.

Install it from the repo root:

```bash
python3 -m pip install -e "packages/contracts[dev]"
```

Contract changes ship as a pull request to `packages/contracts` with a semantic version bump. Other services import this package and do not redefine its models or vocabulary.

Core Phase 1–2 lives under `services/core`. Copy `.env.example` and start the stack with `docker compose up --build`. The default trading mode is `PAPER`. `LIVE` is not enabled. Alembic migrations in `services/core/db` use the same review gate as contract changes.

Phase 4 turns stored signals into a paper fill. `PAPER_STARTING_CASH` is in `.env.example`. The worker's paper clock is the latest completed candle end, not the wall clock. Fees, slippage, and quantity 1 are placeholders.
