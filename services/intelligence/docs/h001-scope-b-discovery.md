# H001 Scope B dependency discovery (2026-10-13)

Discovery only. No train, no H001 execution, no new vendor purchase, no holdout, no secrets.

Verified against repo + freeze + [`h001-prep-handoff.md`](h001-prep-handoff.md):

| Flag | Current |
|---|---|
| `DATA_PREP_READY` | **NO** |
| `READY_TO_RUN` | **NO** |
| Required scope (this project's working assumption) | **B** — PIT earnings **values** |
| Available freeze | **A** — announcement tape |
| Protocol target / features / horizon / decision / entry | **UNFROZEN** (`DRAFT_UNAPPROVED`) |

Gate 2 `DATA READY` remains **withdrawn**.

---

## 1. Existing source / provider inventory

| Capability | Status | PIT / restatement | Owner |
|---|---|---|---|
| `FundamentalProvider` + `FundamentalDataPoint` | **Integrated** (`packages/contracts` 1.0.0) | Query is `available_at <= as_of`. Restatements = **new** `source_id` rows (append-only store). Schema has no original/revision enum. | Contracts (shared); Intelligence implements store |
| Fixture fundamentals | **Integrated**, 5 symbols × 2 EPS rows | Demo PIT only (`metadata.fixture`, `not_historical_nse_vintage=true`) | Intelligence |
| `csv-live` loader | **Integrated**, PAPER/SHADOW/LIVE only | PIT **only if the CSV already is a vintage**. BACKTEST refuses `csv-live`. No file configured in `.env.example`. | Intelligence |
| RSS news | **Integrated** (live news, not EPS) | `published_at` / `retrieved_at`; not Scope B | Intelligence |
| NSE announcement freeze | **Present** gitignored | Scope A clocks; no EPS | Intelligence / Gate 2 extract |
| NSE financial-results freeze | **Present**, auxiliary, **not merged** | 49 files, **2 empty** (HDFCLIFE, SBILIFE). **5,844** rows. **0** rows with an `eps` key. Fields: `toDate`, `filingDate`, `exchdisstime`, `oldNewFlag` (`N` 3631 / `None` 2213), `reInd` (`N/I/-/A/F`), `xbrl` URL. Live vendor table, not a restated EPS vintage. | Same freeze |
| NSE XBRL instance download | **Not implemented**, URLs present on results rows | Would still need PDF-vs-XBRL lag policy (2024 up to 24h). **Not fetched** (no new download authorization). | Unassigned |
| ProwessDx / ACE / FactSet / FMP / Yahoo | Documented in [`h001-source-audit.md`](h001-source-audit.md) | **Not configured.** No env keys, no adapters. Prowess vintage clock is **not** market `available_at`. FMP/Yahoo not first-print. | Unassigned / budget |
| Licensed credentials | `.env.example`: empty `LLM_API_KEY`, no CMIE/FMP/Prowess vars | LLM empty ≠ fundamentals vintage. **No licensed fundamentals account in this service config.** | Operator |

Default Compose: `INTELLIGENCE_DATA_SOURCE=fixtures`. A live EPS HTTP API is **not** in Intelligence.

---

## 2. Exact Scope B requirements

### EarningsAgent (code)

[`earnings.py`](../src/intelligence_agents/agents/earnings.py) calls `fundamental_provider.get_fundamentals(symbol, as_of)` then:

- Uses **all** returned `FundamentalDataPoint`s (any `metric`).
- For scoring: `metric == "eps"` sorted by provider order; needs **≥2** EPS points and nonzero previous for growth.
- Also consumes PIT **news** text (optional LLM). Missing both points and articles → `insufficient_data`.

Contract fields required per point: `symbol`, `metric`, `value`, `unit`, `period`, `announced_at`, `available_at` (aware, `>= announced_at`), `source`, `source_id`, `metadata`.

Implementation-plan metrics when present: `eps`, `revenue`, `profit`, `pe`, `pb`, `roe`, `roce`, `debt`, `cash_flow`; periods `FY2024` / `Q1FY2025`.

### Research objective (source audit)

H001 asked for 49 snapshot names, `available_at` in 2024-01-01 … 2025-12-31 meaning **first time the market could observe the fact**, plus **value fields** and **revision/version**. Announcement existence is **not** that.

**Missing vs agent + objective**

| Need | In freeze / fixtures |
|---|---|
| Historical EPS (49 names × 2024–2025) | Fixtures: 5 names, 2 periods. Freeze results JSON: **no EPS column** |
| `available_at` = first public print | Unproven (`exchdisstime` proxy on announcements; results `filingDate` / XBRL lag) |
| Reconstruct value known at time t | No versioned EPS series |
| Original vs restated values | `oldNewFlag` is `N` or null; not Original/Revision EPS |
| Universe 49 | Results endpoint empty for 2 names; announcements 49/49 |

---

## 3. Qualification matrix

| Source | Hist. EPS | First-print clock | As-of reconstruct | Revisions | 49×window | Licence / access | Verdict |
|---|---|---|---|---|---|---|---|
| Contract fixtures | 5×2 demo | Fixture timestamps | Yes inside demo | No | No | n/a | **Not research data** |
| csv-live | Only if operator supplies vintage CSV | Only if CSV clocks are true | Only if CSV is append-only versions | Only if encoded as new `source_id` | Unknown | Operator file | **Insufficient unless a qualified CSV exists** (none configured) |
| NSE announcements freeze | No | Candidate `exchdisstime` | Event ids only | Separate `seq_id`s, not EPS | 49 names announcements | Already frozen | **Scope A only** |
| NSE financial-results freeze | **No numeric EPS** | `exchdisstime` / `filingDate` / `broadCastDate`; not certified | Cannot replay values | `oldNewFlag` N/null | 47/49 files nonempty | Already frozen | **Insufficient for Scope B values** |
| NSE XBRL via `xbrl` URLs | Possible if instances parsed | `filedAt` can lag PDF in 2024 | If every instance kept | Original vs Revision in XBRL Q&A | Incomplete without download | Public site; **not authorized this task**; rate limits | **Not qualified** (no sample instance fetched) |
| CMIE ProwessDx | Yes (expected) | **No** (vintage calendar) | Vendor-vintage PIT, not NSE print | Cross-vintage restatements | Expected | Paid academic; **not subscribed here** | **Not `available_at` authority**; values cross-check only if licensed |
| FMP / Yahoo / retail | Unverified 49 | No | Often overwrite | Weak | Unknown | Not configured | **Not suitable** |
| BSE DissemDT | n/a | Corroboration clock | n/a | n/a | Dual-list mapping | Not pulled | **Not pulled** |

No source is **qualified** for Scope B. No purchase made.

---

## 4. Dependency / approval requests

**Data/source owner (unassigned; college/project sponsor):**

- Approved provider or dataset for 49 NIFTY names, 2024–2025 EPS (and any other required metrics)?
- Does it preserve **original publication / availability** to the second, or only period-end / vendor load?
- Original vs restated rows with stable ids?
- Licence, credentials, budget, who signs access?
- Authorize NSE XBRL bulk download + storage, or forbid it?

**H001 research / protocol owner (Quant + supervisor):**

- Is Scope B **mandatory**, or may H001 be **re-scoped to A** (event tape only)?
- Target, horizon, decision time, entry price?
- Who freezes the protocol?
- Are `exchdisstime` IST convention and 47 §16 holes acceptable **if** scope becomes A?

**EarningsAgent / Intelligence (Dev1):**

- Reuse `FundamentalDataPoint` + append-only store; **do not** change contracts without a contracts PR.
- Acceptance: fixtures still PIT; BACKTEST never reads live CSV; research CSV/XBRL must set `available_at` from a documented clock; restatements new `source_id`; `metadata.not_historical_nse_vintage` only when true.
- Integration tests: two EPS vintages, as_of hides the later; restated EPS does not overwrite.

Do not treat this file as those approvals.

---

## 5. Recommended next implementation

**Outcome C, with a parallel D decision.**

C — **No approved Scope B source.** Do not build an XBRL/Prowess adapter that assumes data we do not have. Keep work limited to: Scope A prep (already done), this discovery, contracts reuse, and approval packets.

D — If the research owner states H001 is **event occurrence**, not surprise/EPS, request **explicit** re-scope to A. Do **not** change the objective in code until that writing exists.

Not A (nothing qualified). Not B-as-implementation until a named dataset is licensed or XBRL fetch is authorized **and** a sample instance proves values + clocks.

If C later becomes A after a qualified dump: minimal path is load into existing `csv-live`/`fixtures` PIT CSV (BACKTEST via fixtures path) with documented `available_at`, not a new live API.

**Acceptance for a future Scope B adapter (when source exists):** 49-name coverage table; original vs restated EPS; `available_at` evidence (not period_end); hashes; fixtures unchanged; `DATA_PREP_READY` still NO until those pass **and** protocol fields freeze.

**Highest-priority next action:** research owner answers Scope B vs A; sponsor answers licence/XBRL authorization. Do not execute H001.
