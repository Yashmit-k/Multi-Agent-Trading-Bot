# Deploying to a Linux VM

This puts the whole stack on one VM behind Caddy with automatic HTTPS. The public URL serves the dashboard. The browser reaches Core only through the Next.js proxy route (`apps/frontend/src/app/api/v1/[...path]/route.ts`). That route adds the Core token on the server, blocks `/api/v1/internal/*` and the Zerodha login routes, and refuses every POST unless the path is listed in `FRONTEND_ALLOW_POST_PATHS`. A visitor cannot start paper trading. Live trading stays off: `live_enabled` is hard-coded false.

## 1. Create the VM

- Ubuntu 22.04 or 24.04, at least 2 vCPU, 4 GB RAM and 30 GB disk. Any provider works: AWS EC2, GCP, Azure, DigitalOcean, or Oracle free tier.
- Open inbound TCP 22, 80, and 443.
- Hostname:
  - With a domain, add an A record pointing at the VM's IP.
  - Without one, use `<ip-with-dashes>.sslip.io` (for example `203-0-113-7.sslip.io`). It resolves to that IP with no setup.

## 2. Install Docker and clone

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker
git clone https://github.com/Yashmit-k/Multi-Agent-Trading-Bot.git
cd Multi-Agent-Trading-Bot
git checkout submission/assessment-deliverables   # or main after merge
```

## 3. Secrets (operator only)

Copy your local `.env` to the VM yourself, for example with `scp .env vm:Multi-Agent-Trading-Bot/.env`. Then append:

```bash
DOMAIN=203-0-113-7.sslip.io
# Optional: real LLM for the intelligence agents (any OpenAI-compatible endpoint).
# Without these the intelligence agents use the deterministic fixture provider.
# LLM_BASE_URL=https://.../v1
# LLM_API_KEY=...
# LLM_TIER1_MODEL=...
# LLM_TIER2_MODEL=...
```

Do not commit `.env`.

## 4. Restore the database (optional, keeps history)

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d postgres
docker compose cp artifacts/db-backups/core-20261013T100523IST.dump postgres:/tmp/core.dump
docker compose exec postgres pg_restore -U core -d core --clean --if-exists /tmp/core.dump
```

`artifacts/` is not in git. Copy the dump with `scp` first. Without a restore, Core seeds the schema and history on its first start.

## 5. Start

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml ps
```

This starts:
- postgres, redis, core-api (plus the market-data collector)
- trace-recorder
- quant (5 rule agents)
- intelligence (4 agents)
- frontend
- caddy

core-worker does **not** start.

## 6. Zerodha login (daily)

Kite access tokens expire every day. Core API is bound to the VM's loopback only. Tunnel to it from your laptop:

```bash
ssh -L 8000:127.0.0.1:8000 user@vm
```

Then open `http://127.0.0.1:8000/api/v1/zerodha/connect` with your Core token, follow `login_url`, and let Kite redirect to the callback. The redirect URL registered in the Kite developer console must match.

## 7. Smoke test

```bash
deploy/smoke.sh https://203-0-113-7.sslip.io
```

It checks:
- the frontend health route;
- `live_enabled=false`;
- the trace endpoint and agent signals;
- that `POST /api/v1/paper/start` is refused with 403;
- that the main pages render.

## 8. Paper worker (only with explicit authorization)

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml --profile worker up -d core-worker
# stop it again
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml stop core-worker
```

The worker enters new positions only from 09:20 to 10:30 IST, at most 6 entries per IST day, at most ₹20,000 per BUY, and never short.

## Keeping it up for demo day

Every service has `restart: unless-stopped`, except the worker. After a VM reboot, Docker brings the stack back. Re-do the Zerodha login each trading day before 09:15 IST, or the dashboard shows market data as stale.
