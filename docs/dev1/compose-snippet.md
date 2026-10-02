# Compose snippet for Developer 3 — Intelligence

Do not use a service-directory build context. `packages/contracts` must be available.
Do not edit the root `docker-compose.yml` from this snippet; Developer 3 owns that file.

## PAPER bring-up (local, free)

1. Start Ollama on the host: `ollama serve` then `ollama pull qwen2.5:7b`.
2. From the repo root:

```text
docker compose -f docker-compose.yml -f docker-compose.intelligence.yml up --build -d postgres redis core-api core-worker intelligence
```

3. Overlay file: [docker-compose.intelligence.yml](../../docker-compose.intelligence.yml). It sets PAPER serve, fixtures (not RSS), Core ingest URL `http://core-api:8000`, token `change-me` (same as root `.env.example`), and Ollama via `host.docker.internal:11434/v1` with `LLM_API_KEY=ollama` (placeholder, not a paid key). `extra_hosts: host.docker.internal:host-gateway` lets Linux containers reach the host; on Mac/Windows it is harmless.
4. Health: `GET http://localhost:8101/health` — expect `llm_mode=openai`, `llm_host=host.docker.internal` once Ollama env is set. BACKTEST oneshot without a sink still returns `degraded` / `no_signal_sink`.
5. `INTELLIGENCE_EVAL_INTERVAL_SECONDS=3600` so one cycle runs at startup; `as_of` is bucketed to that interval so a rerun with unchanged inputs is idempotent. Stop the container after `/health` shows `last_run_at`.
6. Startup refusal: overlay with `INTERNAL_SIGNAL_TOKEN` empty exits non-zero (`PAPER/SHADOW/LIVE serve requires CORE_API_URL and INTERNAL_SIGNAL_TOKEN`).
7. Local Ollama: `LLM_TIMEOUT_SECONDS=30` as specified. `qwen2.5:7b` needs ~8GB RAM; if the host is already running Core (this machine had ~7.7GB total / ~230MB free), the model will not stay resident, OpenAI `/v1` calls time out, and `FallbackProvider` degrades to FixtureLLM (`llm_fallback` in JSON logs). Timeout `1s` and a dead port both take that path without raising. When RAM is available, Intelligence uses Ollama native streaming (`/api/generate`) for local hosts on port 11434 so CPU decode can finish under the timeout; `/v1` remains the configured OpenAI-compatible base URL.
8. BACKTEST remains FixtureLLM-only. Do not set `INTELLIGENCE_SERVICE_MODE=serve` with BACKTEST.

## Env keys (placeholders only)

See [services/intelligence/.env.example](../../services/intelligence/.env.example): `INTELLIGENCE_SERVICE_MODE`, `INTELLIGENCE_EVAL_INTERVAL_SECONDS` (default 300), `INTELLIGENCE_SYMBOLS`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_TIER1_MODEL`. Daily budget `0` means local/free: token counts are still logged, USD estimate is 0, tier2 stays off.
