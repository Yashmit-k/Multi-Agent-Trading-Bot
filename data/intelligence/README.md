# Real fundamentals for the Fundamental, Valuation, and Earnings agents

Put the file here as `fundamentals.csv`. The intelligence service reads it every cycle (idempotent: rows are keyed by `source_id`). If the file is absent, those agents produce "insufficient data" and stay excluded from fusion.

**The numbers in `fundamentals.template.csv` are placeholders showing the format, not real figures.** Do not copy them.

## Columns

| Column | Meaning |
|---|---|
| `symbol` | NSE symbol as used in this repo (e.g. `INFY`, `M&M`, `BAJAJ-AUTO`) |
| `metric` | one of `eps`, `revenue_growth`, `profit_growth`, `margin`, `roe`, `roce`, `debt`, `cash_flow` |
| `value` | a number; growth, margins, and returns as fractions (`0.074` = 7.4%), `eps` in rupees |
| `unit` | `INR` or `ratio` |
| `period` | e.g. `2026Q2` or `FY2026` |
| `announced_at` | when the company published the result, with timezone (e.g. `2026-10-16T16:00:00+05:30`) |
| `available_at` | when the system may use it. Must not be earlier than `announced_at`; agents never see a row before this time |
| `source` | where it came from (`nse-results`, `annual-report`, `screener-export`, ...) |
| `source_id` | unique id for the row, e.g. `INFY-2026Q2-eps` |

What each agent needs:
- **Valuation:** at least the latest `eps`. The price comes live from Zerodha through Core.
- **Earnings:** `eps` for at least two consecutive quarters, plus the live RSS news it already reads.
- **Fundamental:** any of the metrics above.

## Check, load, and switch on

```bash
python scripts/validate_fundamentals_csv.py data/intelligence/fundamentals.csv
```

On the server, copy the file to `~/Multi-Agent-Trading-Bot/data/intelligence/fundamentals.csv`. It is picked up within one cycle (10 minutes), with no restart.

To let these agents vote in trades, set `FUSION_EXCLUDED_AGENTS=ml` and restart only the worker and frontend:

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml --profile worker up -d --no-deps core-worker frontend
```
