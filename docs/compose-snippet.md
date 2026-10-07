# Compose snippet for Developer 3

Do not use a service-directory build context. `packages/contracts` must be available.

```yaml
  quant:
    build:
      context: .
      dockerfile: services/quant/Dockerfile
    ports:
      - "8102:8080"
    env_file: services/quant/.env.example
    environment:
      QUANT_TRADING_MODE: PAPER
      CORE_API_URL: http://core-api:8000

  frontend-mock-api:
    build:
      context: .
      dockerfile: apps/frontend/mock-api/Dockerfile
    ports:
      - "8090:8090"

  frontend:
    build:
      context: .
      dockerfile: apps/frontend/Dockerfile
    ports:
      - "3000:3000"
    environment:
      NEXT_PUBLIC_API_BASE_URL: http://core-api:8000
```
