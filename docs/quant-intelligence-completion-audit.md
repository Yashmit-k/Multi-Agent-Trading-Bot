# Quant and Intelligence completion audit

Date: 2026-10-12. Read-only. Committed HEAD is `ad7557f`. Local uncommitted work includes the quant API health wait, the intelligence fixture skip, the quant image's local `core-features` install, and the submission notes. This audit did not change application code, frontend code, trading behavior, configuration, or any existing document.

No Docker container was started or restarted. No H001 fit, label, feature build, backtest, or holdout read was performed. No order was sent.

## 1. Executive summary

The paper path is implemented and covered by in-memory tests: five quant rule agents, four intelligence agents, signal ingestion with duplicate `signal_id` rejection, fusion, a proposal id that is final once stored, risk that accepts `PAPER` only, and paper execution that fills at the next stored open. `live_enabled` is hard-coded false in the core API. This audit found no path that calls `place_order` or `KiteTicker`.

Neither subsystem is fully complete as a live-data product. The Compose intelligence service always builds quotes from the five-symbol fixture provider. RSS and CSV loaders exist and are unit-tested, and the serve loop does not call them. `MlAgent` is not in the paper agent list. H001 is a separate research package with synthetic tests; it is not wired into paper trading, and execution stays unauthorized because the recorded training minority class is 34 against a bar of 50.

No P0 or P1 defect was found. The remaining work before October 14 is demonstration evidence and documentation accuracy, not a change to trading behavior.

## 2. Quant feature matrix

| Feature | Status | What it is supposed to do | Source | Tests | Evidence and gap | Essential by Oct 14 | Next action |
|---|---|---|---|---|---|---|---|
| Quant HTTP service | IMPLEMENTED AND TESTED | Serve `/health` and, in PAPER with tokens, publish signals | `quant_agents.service.create_app`, `_publish_loop` | `services/quant/tests/unit/test_health.py` | Health is `ok` when a sink exists and `degraded` / `no_signal_sink` otherwise. PAPER, SHADOW, and LIVE refuse to start without a sink. This audit re-ran the health tests: passed. | Yes | None for startup. |
| `core-features` in the quant image | IMPLEMENTED — PARTIALLY VERIFIED | Install the local feature engine, not PyPI | `services/quant/Dockerfile` | None in this audit | The Dockerfile copies `services/core/feature-engine` and installs it editable before quant. A prior image build in this working tree succeeded. This audit did not rebuild the image. | Yes, already present | Do not remove the copy. |
| Startup wait for the core API | IMPLEMENTED AND TESTED | Do not treat a refused connection as a failed paper cycle that waits 300 seconds | `wait_for_core_api`, `fetch_feature` in `paper.py`; Compose `core-api` healthcheck and quant `depends_on` | `test_paper.py` | Up to 20 health attempts, one second apart. Feature GET retries only on `httpx.TransportError` (3 attempts). A received HTTP response is not retried. This audit re-ran `test_paper.py`: 4 passed, including refused health with zero submits and one successful pass after a refused connection. | Yes | None. |
| Paper pass logging | IMPLEMENTED — PARTIALLY VERIFIED | Distinguish not-ready, skip, success, and failure | `quant_core_api_not_ready`, `quant_core_api_unavailable`, `quant_feature_unreachable`, `quant_skip_symbol`, `quant_paper_pass`, `quant paper pass failed` | The unit tests cover the not-ready and success paths | An exception inside `publish_symbol_signals` aborts the rest of that pass; the loop logs the exception and sleeps `QUANT_EVAL_INTERVAL_SECONDS` (300 in Compose). There is no per-agent isolation inside one symbol. | No | P2: optional per-agent catch. Duplicate `signal_id`s make the next cycle safe. |
| Feature consumption | IMPLEMENTED AND TESTED | Read a Core `FeatureSet` and do not recompute 1.1 formulas in the agents | `fetch_feature`, `_OneFeatureProvider`, `BaseQuantAgent` | `tests/test_dev3.py` (`test_agents_do_not_compute_feature_set_1_1_fields`, `test_future_bar_is_excluded`, `test_short_history_omits_indicators_and_marks_imbalance_unavailable`) | `get_feature_set` raises `LookupError` when the set is missing or its timestamp is after `as_of`. A 404 from Core skips the symbol (`quant_skip_symbol`). `volume_imbalance` is marked unavailable by the engine (`FEATURE_VERSION` `1.1.0` in `core_features.engine`). Contract fixtures still label their own sample feature version `1.0.0`. That is the fixture generator, not the engine the paper pass calls. | Yes | Do not mix the two version strings in a demo script. |
| Five rule agents | IMPLEMENTED AND TESTED | Technical, Momentum, Mean Reversion, Volume, and Regime emit `AgentSignal` | `paper._AGENTS`, `quant_agents.agents` | `services/quant/tests/unit/test_agents.py`, `test_publish_uses_core_features_for_each_agent` | `publish_symbol_signals` evaluates those five classes and submits each result. Regime without index symbols does not invent an index view; Compose passes `regime_index_symbols: ()`. `test_agents.py` was not re-run in this audit. The publish test was re-run and passed. | Yes | None. |
| `MlAgent` | INTENTIONALLY DEFERRED | Not part of the paper vote | `quant_agents.ml.agent.MlAgent` | `services/quant/tests/unit/test_ml.py` (not re-run) | The class exists. `_AGENTS` does not include it. Direction research docs say OHLCV direction research is closed. | No | Leave unloaded. |
| Signal id and duplicate submit | IMPLEMENTED AND TESTED | One identity hash per agent, symbol, horizon, timeframe, `as_of`, and input hash | `BaseQuantAgent._build_signal` | Ingestion duplicate behavior is in `tests/test_phase4.py` | Quant's `CoreSignalSink.submit` posts once and calls `raise_for_status`. It does not retry. Core `ingest_signal` returns `duplicate=true` when `signal_id` is already stored. A later cycle does not create a second row. | Yes | None. |
| Risk before paper execution | IMPLEMENTED AND TESTED | `assess` accepts `PAPER` only; buys fit cash and 100,000; no shorts | `core_risk.assess`, `core_paper.cycle.run_paper_cycle` | `tests/test_phase4.py`, `tests/test_dev3.py` | Re-ran in this audit: 31 passed. `assess` records `metadata.kill_switch = "noop"`. The real kill switch is `repository.kill_switch_armed` inside `run_paper_cycle`, tested by `test_kill_switch_queues_a_flatten_and_waits_for_the_next_bar`. The comment at the top of `assess.py` is stale relative to `cycle.py`. | Yes | Do not "fix" the comment during the demo. The behavior under test is the cycle, not that metadata field. |
| Paper fills and persistence | IMPLEMENTED AND TESTED | Next stored open, unfilled if no later bar, 2 bp unless an explicit schedule, stop-first, deterministic proposal and order ids | `run_paper_cycle`, `proposal_id_for`, `order_for_proposal` | `test_paper_cycle_fills_once_and_ignores_late_signals`, `test_unconfigured_paper_cost_is_two_bps_and_explicit_zero_stays_zero`, `tests/test_backtest.py` | Tests use `sqlite://` via `tests/conftest.py`. They do not use the Compose Postgres volume. A stored proposal is reused. An existing order for that proposal is not created again. | Yes | P2: show one stored order from the running API before the demo. This audit did not query it. |
| `live_enabled` and mode | IMPLEMENTED AND TESTED | Paper only | `core_api.app` status routes; `assess`; worker reads `TRADING_MODE` | `test_non_paper_modes_are_rejected` | API status returns `live_enabled: false`. `GET /health` returns only `{"status":"ok"}`. Compose sets `QUANT_TRADING_MODE=PAPER`. A worker started with another mode still fails `assess` for non-PAPER. | Yes | Demo `GET /api/v1/system/status`, not `/api/v1/health`. |
| Replay and backtest | IMPLEMENTED — PARTIALLY VERIFIED | Same fill rule as paper; hide bars with `end > as_of`; refuse the holdout snapshot | `core_paper.backtest`, `quant_agents.replay`, `core_market_data` snapshot open | `tests/test_backtest.py` (re-run, passed), `test_bar_visible_hides_a_later_end` | Passing unit tests are not a validation of a research result. This audit did not run a backtest. Quant `data_source=historical` attaches replay on the app; the paper loop does not use that object. It reads Core features. | The shared fill rule is essential. A new backtest run is not. | Do not start a research backtest for the submission. |
| H001 package | INTENTIONALLY DEFERRED | Not a paper agent. Execution is not authorized. | `quant_agents.research.h001` | `services/quant/tests/unit/test_h001_*.py` | Not imported by `research/__init__.py` into the paper loop. Not in `_AGENTS`. This audit did not run those tests and did not open frozen tapes. Recorded eligibility remains `INCONCLUSIVE` (training minority class 34, bar 50). | No | Do not fit or weaken the bar. |

`QUANT_DATA_SOURCE=fixtures` in Compose does not mean the paper pass uses fixture candles. `create_app` attaches historical replay only when `data_source == "historical"`. The publish loop always GETs `/api/v1/features/{symbol}`.

## 3. Intelligence feature matrix

Fixture symbols, confirmed in `packages/contracts/src/contracts/fixtures.py`: `RELIANCE`, `TCS`, `INFY`, `HDFCBANK`, `ICICIBANK`. Compose `INTELLIGENCE_SYMBOLS` is still the NIFTY 50 anchor `*nifty50`, including `TRENT`. The runner was not changed to drop names.

| Feature | Status | What it is supposed to do | Source | Tests | Evidence and gap | Essential by Oct 14 | Next action |
|---|---|---|---|---|---|---|---|
| Intelligence service | IMPLEMENTED AND TESTED | Serve mode runs an evaluation loop; PAPER without a token refuses to start | `intelligence_agents.service.create_app`, `loop.evaluation_loop` | `services/intelligence/tests/test_sink_service.py` (not re-run), `test_runner.py` (re-run) | `/health` reports runner, sink, and LLM fields. Serve mode requires PAPER, SHADOW, or LIVE and a sink. This audit did not restart the container. | Yes | None. |
| News agent | IMPLEMENTED — PARTIALLY VERIFIED | Score visible articles. Empty input emits an insufficient signal, not an invented article. | `NewsAgent.evaluate`, `IntelligenceNewsProvider` | `test_agents.py`, `test_news_store.py` (store tests not re-run) | Compose `INTELLIGENCE_DATA_SOURCE=fixtures` loads `all_articles` for the five fixture symbols only. Other symbols get no articles and `_insufficient` (score 0, `insufficient_data`), which is still submitted. That zero signal is explicit, not a fabricated story. | Yes, in fixture mode | Say in the demo that non-fixture names have no fixture news. |
| RSS acquisition | PARTIALLY IMPLEMENTED | Pull and normalize RSS when configured | `RssPuller` in `news/rss.py` | `test_rss.py` (not re-run) | Settings accept `INTELLIGENCE_DATA_SOURCE=rss` and require `NEWS_RSS_URLS`. `make_stores` only loads fixtures when the source is `fixtures`. No serve path calls `RssPuller`. | No | P3. Do not switch Compose to RSS for the demo. |
| Fundamentals agent | IMPLEMENTED — PARTIALLY VERIFIED | Use points with `available_at` at or before `as_of`. Missing points become an insufficient signal. | `FundamentalAgent`, `IntelligenceFundamentalProvider.points_for` | `test_agents.py`, `test_fundamentals.py` (`test_q1_hidden_until_available`, not re-run) | Fixture load is the five symbols. The score uses EPS/100 clipped to [-1, 1]. It is a heuristic. The code does not claim the figures are current filings. | Yes, as a fixture heuristic | Do not describe it as live fundamentals. |
| CSV fundamentals | PARTIALLY IMPLEMENTED | Load a CSV into the store | `fundamentals/csv_loader.py` | `test_csv_loader` (not re-run) | Nothing in `runtime.make_stores` calls `load_csv`. | No | P3. |
| Earnings agent | IMPLEMENTED — PARTIALLY VERIFIED | Combine visible EPS points and visible news. This is not H001. | `EarningsAgent.evaluate` | `test_fundamental_valuation_earnings` | Two EPS points can add a clipped growth term. News text is interpreted by the fixture LLM when no API key is set. Missing both inputs yields `_insufficient`. Malformed provider exceptions are caught by the runner as `agent_failed` and do not stop other agents. | Yes, as a fixture agent | Do not cite it as an earnings-timing result. |
| Valuation agent | IMPLEMENTED AND TESTED | PE from the quote and EPS. No quote means no valuation signal. | `ValuationAgent.evaluate`, `FixtureCoverageError` | `test_valuation_coverage.py` (re-run, 3 passed) | `KeyError` and `LookupError` from `get_quote` become `FixtureCoverageError`. The runner logs `fixture_symbol_skipped` and does not submit. A quote with no positive EPS uses `_insufficient` and does submit a zero signal. That path does not invent a price; it refuses to score. `make_runner` always passes `FakeMarketDataProvider`. There is no production quote client in the serve path. | Yes | Keep the NIFTY 50 list. Do not add fixture prices for the other names. |
| Runner isolation | IMPLEMENTED AND TESTED | One agent or one missing fixture symbol does not drop the other agents | `Runner.run` | `test_runner_skips_unsupported_symbols_and_keeps_supported_ones`, `test_runner_submits_fixture_signals`, `test_runner_duplicate_signal_id_is_ok` | `FixtureCoverageError` skips. `LeakageError` in BACKTEST re-raises. Other exceptions log `agent_failed` and continue. A rejected, non-duplicate submit raises `RuntimeError` and stops the rest of that cycle. The loop records `eval_cycle_failed` and waits for the next interval. | Yes | None. |
| Signal ids and sink retries | IMPLEMENTED AND TESTED | Stable id from agent, version, symbol, `as_of`, horizon, and input hash. HTTP retries do not create a second stored row. | `signal_id.make_signal_id`, `HttpSignalSink.submit`, `ingest_signal` | `test_signal_id_changes_when_inputs_change`, `test_http_retries_5xx` (sink file not re-run this audit), phase-4 duplicate coverage | The sink retries `HTTPError`, including HTTP 500, up to 3 times. Core treats an existing `signal_id` as a duplicate and does not insert again. A 422 returns `invalid_schema` without retry. A lost connection after a successful insert is safe because the retry sees the stored id. | Yes | None. |
| Fixture LLM | IMPLEMENTED AND TESTED | Deterministic stand-in when no provider key is configured | `FixtureLLMProvider`, `build_router` | `test_llm.py` (not re-run), agent tests use it | Compose sets empty `LLM_API_KEY` and `LLM_BASE_URL`. That is fixture interpretation, not a live model. | Yes | Do not present LLM scores as a paid-provider run. |
| Schedule | IMPLEMENTED AND TESTED | Bucket wall-clock `as_of` so a rerun in the same interval keeps the same id | `cycle_as_of` | `test_cycle_as_of_is_stable_inside_interval` | Compose interval is 300 seconds. | Yes | None. |

## 4. Cross-service trace

The path that actually runs in Compose:

1. Core stores candles and builds `FeatureSet` 1.1.0 (`core_features.engine.build_feature_set`). Quant does not build those fields.
2. Quant `run_paper_pass` waits for `GET /health`, then `GET /api/v1/features/{symbol}?timeframe=1d` with the read token. Missing features skip the symbol. The five agents evaluate that set and `CoreSignalSink` POSTs `/api/v1/internal/signals` with `X-Trading-Mode: PAPER`.
3. Intelligence does not read that feature route. `make_runner` uses `FakeFeatureProvider` and `FakeMarketDataProvider`, plus fixture news and fundamentals for five symbols. The four agents POST the same internal signal route.
4. `ingest_signal` validates, stores, and publishes once per new `signal_id`.
5. The worker calls `run_paper_cycle`. For each instrument and horizon it takes the latest candle end as `as_of`, fuses signals with `timestamp <= as_of` and `valid_until >= as_of`, keeps the newest signal per agent, and clips the weighted `signal * confidence` aggregate. `build_proposal` uses strategy id `paper-fusion`. Risk runs before an order is inserted. A later bar fills at its open. Ids for proposal, risk, and order are digests, and a second cycle sees the stored row.

Links with end-to-end code plus in-memory tests: ingestion, fusion, risk, fill, kill switch, duplicate signal id.

Links with unit or mock evidence only: quant HTTP feature fetch (mocked transport), intelligence HTTP sink (mocked transport).

Links observed in an earlier Compose run and not rechecked in this audit: quant log `quant_paper_pass` with 245 signals and 50 symbols, and intelligence `fixture_symbol_skipped` for `TRENT` with news, fundamental, and earnings still submitted. This audit did not read container logs.

Not on this path: `MlAgent`, H001, `RssPuller`, CSV fundamentals, and a non-fixture market-data provider for intelligence.

Symbol handling: quant feature lookup and intelligence fixture quotes uppercase through their providers. The NIFTY list in Compose is already uppercase. No second universe list was introduced.

Timestamps: paper `as_of` is the candle end in UTC. Intelligence serve mode uses a UTC wall-clock bucket, not the candle end. The two clocks are different by design. Fusion still drops signals outside the candle's `as_of` window, so an intelligence signal stamped after the latest candle is not selected until a later candle exists. That is consistent with the no-lookahead rule. It can also mean a fresh intelligence cycle is invisible to the current paper candle. That behavior is not separately asserted in a Compose test. It is a P2 demonstration note, not a defect in the selection rule.

## 5. Tests and quality of evidence

Re-run in this audit, all in-memory or mocked, with no holdout path and no Postgres volume:

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest tests/test_phase4.py tests/test_dev3.py tests/test_backtest.py -q` | 31 passed, 1 Starlette deprecation warning |
| Quant `test_paper.py` and `test_health.py` | 8 passed |
| Intelligence `test_valuation_coverage.py`, `test_agents.py`, `test_runner.py` | 14 passed |

Not re-run: frontend vitest (previously reported 12 passed; Developer 2 owns the dashboard), `test_h001_*.py`, research scripts under `tests/test_*rebound*` and the other backtest experiments, `test_live_llm.py`, RSS, CSV, and the broader intelligence LLM file. `test_live_llm.py` is gated and was left alone so this audit would not call a provider.

Strong coverage: paper mode rejection, cash, notional cap, shorts, one fill, kill switch, future-bar hiding, quant health and startup retry, valuation skip versus evaluate, runner duplicate id.

Weak or absent: a test that one quant agent exception still submits the other four agents; a test that the Compose worker has written an order into Postgres; an end-to-end test from a real candle file through both services. Those gaps do not contradict the unit tests.

`tests/conftest.py` builds `sqlite://` and loads the seed. It does not open `snapshots/holdout_after_20261005`.

## 6. Confirmed defects, incomplete features, and external dependencies

Confirmed defects: none that break paper safety or the October 14 paper workflow.

Incomplete, and not required for the paper demo:

- RSS and CSV loaders are not called by the serve loop.
- Intelligence quotes and features in the service are fixture fakes, including when Compose lists 50 symbols.
- `MlAgent` is unloaded.
- H001 is not a trading feature. Execution remains blocked on the recorded sample rule.
- `assess` metadata still says the kill switch is a noop. `run_paper_cycle` is the implementation that arms, blocks new buys, and queues a flatten.

External dependencies for anything beyond the demo: a news RSS endpoint, a fundamentals file or vendor feed, and a separate decision before any H001 fit. Zerodha keys are empty in the intended paper env. `live_enabled` does not become true if those keys are filled.

Earlier Compose evidence (not rechecked here) showed duplicate intelligence submissions (`duplicate: true`) because signal ids were already stored. That is the ingestion rule, not a second order.

## 7. Prioritized next actions

**P0:** none.

**P1:** none. The paper workflow can be demonstrated from the existing services and the in-memory tests. No code change is required to make risk, mode, or duplicate-signal handling safe.

**P2**

- Before the demo, call the running API for system status, one signal list, and one order or an explicit empty order list. Do not reset the database. Evidence required: the JSON bodies, with the token not pasted into notes.
- Tell the audience that intelligence prices exist for five fixture symbols and that other valuation symbols are skipped on purpose.
- Optional small test, only if someone edits `publish_symbol_signals`: an agent that raises should not prevent the other agents' `submit` calls. Not required if that function stays as it is. The current failure mode still retries next cycle under the same `signal_id`.

**P3**

- Schedule `RssPuller` or `load_csv` only if a real source is in scope.
- Attach a Core quote provider to intelligence only with a fixture-versus-production distinction kept in the skip logs.
- Leave `MlAgent` and H001 unwired.

No refactor is recommended.

## 8. Plan through October 14

1. Leave `TRADING_MODE=PAPER` and `live_enabled` false. Do not place a broker order.
2. Leave the NIFTY 50 symbol list and the five-symbol fixture prices as they are.
3. Use the paper demo checklist: `GET /health`, then authenticated `GET /api/v1/system/status`, then signals and orders. Dashboard fixes stay with Developer 2.
4. Do not fit H001, do not open the holdout directory, and do not retune the 2 bp gate.
5. If a compose log shows `quant_core_api_unavailable` after the bounded wait, wait for the next 300-second cycle or restart only the quant container after the API is healthy. Do not delete Postgres.

## 9. Verified versus unverified

Verified in this audit by reading code and re-running the tests listed above:

- Five quant agents are the paper publishers. `MlAgent` is not.
- Startup health wait and transport retry do not resubmit after an HTTP response.
- Valuation does not emit a signal when the fixture quote is missing. A mixed symbol list still evaluates `RELIANCE`.
- Risk rejects non-PAPER, cash shortfalls, the notional cap, and shorts. Paper fills once on fixture candles in SQLite. The kill switch queues a flatten for a later bar.
- Duplicate `signal_id` ingestion does not accept the row twice.
- Fixture symbol tuple is the five names above. Compose still points intelligence at the full NIFTY 50 list.

Unverified in this audit:

- Current container health, current logs, and whether Postgres currently holds a fill.
- Frontend behavior.
- H001 synthetic tests in this working tree (they were not executed).
- Any claim that RSS, CSV, or a live LLM ran.
- The July 2025 acceptance backtest numbers in `docs/current-status.md`. Those figures were not recomputed.

## 10. Conclusion

Quant is suitable for a paper-mode demonstration of five rule agents publishing Core feature signals into the shared paper cycle. It is not a complete research or machine-learning trading system, and it should not be described as one.

Intelligence is suitable for a paper-mode demonstration in fixture mode: four agents submit contract signals, missing fixture quotes are skipped for valuation only, and the other agents keep running. It is not a complete news, fundamentals, or earnings data product. The earnings agent is not evidence for H001.

The evidence does not justify calling either subsystem fully complete. It does justify calling the paper-trading workflow implemented, tested on SQLite and mocks, and safe to demonstrate with live trading left off. No P0 or P1 defect was found.
