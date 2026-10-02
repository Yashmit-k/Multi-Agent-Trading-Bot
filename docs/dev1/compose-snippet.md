# Compose snippet for Developer 3 — Intelligence

Do not use a service-directory build context. `packages/contracts` must be available.
Do not edit the root `docker-compose.yml` from this snippet; Developer 3 owns that file.

```yaml
  intelligence:
    build:
      context: .
      dockerfile: services/intelligence/Dockerfile
    ports:
      - "8101:8080"
    env_file: services/intelligence/.env.example
    environment:
      INTELLIGENCE_TRADING_MODE: BACKTEST
      INTELLIGENCE_DATA_SOURCE: fixtures
      INTELLIGENCE_STORE: sqlite
      INTELLIGENCE_SQLITE_PATH: /var/lib/intelligence/intel.db
    volumes:
      - intelligence-data:/var/lib/intelligence
```

Mount the SQLite volume so news and fundamentals persist across restarts. Retention is unbounded in v1 (revisit at 2 GB).

Local overlay (does not edit this root compose file):

```text
docker compose -f docker-compose.yml -f docker-compose.intelligence.yml up --build -d intelligence
```
