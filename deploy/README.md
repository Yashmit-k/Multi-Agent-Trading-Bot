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

## Gotchas learned on the live deploy

- **Prefer `--no-deps` when updating one service.** `docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build --no-deps <service>` leaves the others running. The Zerodha login is stored in Postgres (`broker_sessions`), so restarting core-api no longer logs you out.
- **Migrations are manual.** After pulling a new revision, run `docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml run --rm --no-deps -w /app/services/core/db core-api alembic upgrade head`.
- **Attach an Elastic IP before relying on the URL.** Without one, a stop/start changes the public IP, and with it the sslip.io hostname and `DOMAIN`.
- **A free Groq LLM needs pacing.** Keep the compose defaults `LLM_MIN_INTERVAL_SECONDS=2.5` and `LLM_REASONING_EFFORT=low` for `openai/gpt-oss-20b`.

## Disk and history retention

- The worker prunes history once a day after 17:00 IST (`core_db/retention.py`):
  - agent signals older than 30 days are summarised into `agent_signal_daily`, then removed (signals cited by trades are kept);
  - trace copies of `agent.signal` messages older than 7 days are removed;
  - `signal_accepted` audit rows older than 30 days are removed.
  Candles, orders, fills and positions are never pruned.
- `deploy/healthcheck.sh` alerts when the disk is 85% full (`DISK_ALERT_PCT`).
- Weekly cron, Sunday 03:00 IST, clears Docker's build cache (images in use are untouched):
  ```
  30 21 * * 6 docker builder prune -f --filter until=168h >> $HOME/backups/maintenance.log 2>&1
  ```

## Notifications (Telegram)

1. In Telegram, message **@BotFather**, send `/newbot`, and copy the bot token.
2. Send any message to your new bot, then open `https://api.telegram.org/bot<token>/getUpdates` and copy `"chat":{"id": ...}`.
3. On the VM, add to `~/Multi-Agent-Trading-Bot/.env`:
   ```
   TELEGRAM_BOT_TOKEN=<token>
   TELEGRAM_CHAT_ID=<chat id>
   PUBLIC_SITE_URL=https://<your DOMAIN>
   ```
4. Restart the worker: `docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml --profile worker up -d --no-deps core-worker`.

You then get:
- a Zerodha login reminder at 08:30 IST, and again at 09:10, on trading days when you are not logged in;
- an end-of-day paper summary after 15:35 IST;
- from `deploy/healthcheck.sh` (cron, every 5 minutes in market hours), an alert when any component is down, including "paper trading is on but the worker is silent", re-sent at most every 30 minutes, plus a "recovered" message.

`ALERT_WEBHOOK_URL` (Slack or Discord incoming webhook) works instead of, or as well as, Telegram.

## Moving to another AWS region (e.g. Sydney → Mumbai)

The server's distance adds about a second to every page from India. `ap-south-1` (Mumbai) removes most of that. The public URL changes with the new IP, so update it anywhere you submitted it.

1. **Prepare (Sydney).**
   - Stop the worker: `docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml --profile worker stop core-worker`.
   - Take a backup: `deploy/backup.sh`. Copy it to your laptop: `scp -i key.pem ubuntu@<sydney-ip>:~/backups/core-*.dump .`
2. **Copy the machine.**
   - EC2 console → Instances → select the instance → *Actions → Image and templates → Create image* (name `stockx-sydney`). Wait until the AMI is *Available*.
   - AMIs → select it → *Actions → Copy AMI* → destination region **Asia Pacific (Mumbai)**. Wait until it is *Available* in Mumbai.
3. **Launch in Mumbai.** Switch the console region to Mumbai.
   - Key pairs are per region. Import your existing key: run `ssh-keygen -y -f ~/Downloads/trading-bot-keypair.pem > trading-bot.pub` on your laptop, then *Key pairs → Actions → Import key pair*.
   - *AMIs → stockx-sydney → Launch instance from AMI*: t3.small, that key pair, a security group allowing TCP 22, 80 and 443.
   - *Elastic IPs → Allocate* and associate the new address with the instance.
4. **Point it at the new address.** SSH in with the new IP.
   - In `~/Multi-Agent-Trading-Bot/.env`, set `DOMAIN=<new-ip-with-dashes>.sslip.io` and `PUBLIC_SITE_URL=https://<that>`.
   - Run `docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d` (Caddy gets a new certificate in under a minute).
   - Start the worker as usual.
   - `crontab -l` should still list `backup.sh` and `healthcheck.sh`. The health check reads `DOMAIN` from `.env`, so it follows the move.
5. **Verify.** Run `deploy/smoke.sh https://<new domain>`. Log in to Zerodha through the tunnel to the new IP. The Kite redirect URL stays `http://127.0.0.1:8000/...` and needs no change.
6. **Clean up Sydney** once Mumbai has run for a day:
   - Terminate the Sydney instance.
   - Release its Elastic IP: unattached Elastic IPs are billed.
   - Deregister the AMIs and delete their snapshots in both regions.

Alternative: launch a fresh Ubuntu instance in Mumbai and follow sections 2–5 of this guide. Copy `.env` across, and restore the backup with `pg_restore -U core -d core --clean core-*.dump` inside the postgres container.

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
