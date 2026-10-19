#!/usr/bin/env bash
# Nightly fundamentals refresh from Yahoo Finance into data/intelligence/fundamentals.csv.
# Cron (EC2 clock is UTC), weekdays 20:30 IST:
#   0 15 * * 1-5  ~/Multi-Agent-Trading-Bot/deploy/fetch_fundamentals.sh >> ~/backups/fundamentals.log 2>&1
# Append-only: existing rows are never rewritten (see services/intelligence/.../fundamentals/yahoo.py).
# The intelligence service picks up new rows on its next cycle; no restart needed.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml run --rm --no-deps \
  -v "$REPO/data/intelligence:/out" intelligence \
  python -m intelligence_agents.fundamentals.yahoo --out /out/fundamentals.csv
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml run --rm --no-deps \
  -v "$REPO/data/intelligence:/out:ro" -v "$REPO/scripts:/scripts:ro" intelligence \
  python /scripts/validate_fundamentals_csv.py /out/fundamentals.csv
echo "$(date "+%Y-%m-%dT%H:%M:%S%z") fundamentals refresh done"
