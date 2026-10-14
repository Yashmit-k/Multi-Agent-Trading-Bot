# Quant + News data readiness

## Purpose and scope

This check asks whether a Quant + News model can be trained from historical, point-in-time news joined to the five Quant rule agents. It stops at that question. No fusion pipeline was built.

## Quant agents and candles

The five rule agents are `technical`, `momentum`, `mean_reversion`, `volume`, and `regime`, from `services/quant/src/quant_agents/agents/`.

Permitted candle paths, from `services/core/market-data/src/core_market_data/replay.py`, are `snapshots 2/nifty50/5m` (`nifty50_5m_20261005`) and `snapshots 2/nifty50/1D` (`nifty50_1d_20261005`). Replaying those agents on those candles is technically possible. That replay produces price-based signals only. It does not create news.

This check did not run that replay.

## NewsArticle contract

`packages/contracts/src/contracts/schemas/news_article.py` keys each article by `article_id`. The other fields are `source`, `title`, `url`, `published_at`, `retrieved_at`, `content_hash`, `symbols`, `raw_text`, and `metadata`. `retrieved_at` cannot be earlier than `published_at`.

`services/intelligence/src/intelligence_agents/news/store.py` returns an article for a decision only when it is not quarantined and both `published_at` and `retrieved_at` are at or before `as_of`. Publication time alone is not availability.

## Fixtures

`all_articles` in `packages/contracts/src/contracts/fixtures.py` builds two template sentences per symbol. The texts are “reported steady operating updates on 2024-06-03” and “announced a result after the fixture as_of.” The timestamps are 2024-06-03 04:00 UTC and 2024-06-04 04:00 UTC. `retrieved_at` is five minutes after `published_at`. The source is `fixture-wire`, and metadata sets `fixture` to true. These rows are synthetic fixtures. They are not a historical news archive and cannot train a Quant + News model.

## RSS and Compose

`services/intelligence/src/intelligence_agents/news/rss.py` turns a live feed item into an article whose `article_id` starts with `rss-` and whose `retrieved_at` is the pull clock. That is an optional live pull. It is not a stored archive of the candle study window. No feed was fetched for this check.

`docker-compose.yml` sets `INTELLIGENCE_DATA_SOURCE=fixtures` for the intelligence service. `docs/dev1/implementation-plan.md` already says long-window news backtests are fixture-bound.

## Locations inspected

Inspected in source or by directory name only:

- `services/quant/src/quant_agents/agents/`
- `services/core/market-data/src/core_market_data/replay.py`
- `packages/contracts/src/contracts/schemas/news_article.py`
- `packages/contracts/src/contracts/fixtures.py`
- `services/intelligence/src/intelligence_agents/news/store.py`
- `services/intelligence/src/intelligence_agents/news/rss.py`
- `docker-compose.yml`
- `docs/dev1/implementation-plan.md`
- `snapshots 2/nifty50` directory names: `1D`, `5m`, `candles.jsonl`, `manifest.json`. No news archive name.
- `datasets` and `datasets/research` directory names. The research folders are prior market studies, including `today_drop_ml_filter`. Names matching `news` or `article` under `datasets`, `snapshots 2/nifty50`, `services/intelligence`, and `docs` were the news agent, its tests, and the `NewsArticle` / `NewsSignal` schema files.

Not inspected:

- `snapshots/holdout_after_20261005`
- The running Postgres database
- The Compose `intelligence-data` volume and `/var/lib/intelligence/intel.db`
- The contents of `datasets/h001-nse-ann-2024-2025-v1` and `datasets/h001-pit-events-nse-ann-2024-2025-v1.parquet`. Those names were seen and the files were not opened. They belong to the blocked H001 study and are not a `NewsArticle` archive for this experiment.

Absence is claimed only for the locations that were inspected. Uninspected locations are not described as empty.

## Minimum archive before any fit

A later attempt needs a stored archive, not fixtures and not a live RSS pull, with:

- Stable `article_id` values
- Source provenance
- A reliable symbol map
- `published_at` and `retrieved_at` (or an equivalent availability time that is not silently treated as the publication time)
- Reproducible article text or scores
- Measured coverage that overlaps the permitted candle window

Missing news must stay missing. It must not be filled in as neutral sentiment.

## Why fitting stops

Model B cannot be compared with a Quant-only model until both see the same decisions and the news features are limited to articles available at those decisions. The inspected stores do not provide that history. Fitting now would train on template sentences or on a feed that was not retained for the study window.

The running database was not queried. No model was trained. No artifact was created or changed. No backtest or replay was run. H001 was not executed. The prohibited holdout was not accessed. The running stack was not modified.

INSUFFICIENT HISTORICAL NEWS DATA
