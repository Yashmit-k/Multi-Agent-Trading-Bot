# H001 Historical Earnings/Events Source Audit

Status of this audit: **source discovery**. Candidate-source analysis below is unchanged. No labels were created, no target/features/horizon were frozen, and no market snapshots were modified.

**Later overlay (Task 3 documentation reconciliation):** a Gate 2 NSE freeze was subsequently acquired (see [`h001-data-readiness.md`](../../quant/docs/h001-data-readiness.md)). That freeze does **not** make H001 PIT-ready. Gate 2’s `DATA READY` conclusion is **withdrawn**. This discovery document is **not** an extract audit and does **not** independently verify the freeze.

Project state:

- `DATA NOT READY`
- `EVENT_DATA_BLOCKED` (timestamp semantics, immutability, 49×quarter coverage, and restatement-safe values remain unproven)
- `H001 = BLOCKED_PRECONDITION`
- `READY_TO_RUN = NO`

## 1. Objective

Determine whether we can obtain **trustworthy point-in-time historical earnings/events data** for the **49 NIFTY50 names that have bars** in the frozen market snapshots, with event **availability during 2024-01-01 through 2025-12-31**.

The deciding requirement is an `available_at` timestamp that means:

> the first time this information was actually available to the market / a backtest

This is **not** the same as period end, retrieval time, vendor load time, or a guessed offset from an announcement date.

This repository does **not** currently contain such a **PIT-certified** dataset. A later Gate 2 NSE freeze exists under gitignored `datasets/`; it is **not** that certified dataset (Gate 2 `DATA READY` withdrawn). Fixture fundamentals in `packages/contracts/src/contracts/fixtures.py` (`metadata.fixture = true`) are test data and are not evidence of historical PIT coverage.

## 2. Required universe

Taken from the frozen manifests (symbols with `count > 0` only). The two manifests agree.

| Snapshot | Path | Symbols with bars | Excluded |
|---|---|---|---|
| `nifty50_1d_20261005` | `snapshots 2/nifty50/1D/manifest.json` | 49 | `TATAMOTORS` (`count = 0`) |
| `nifty50_5m_20261005` | `snapshots 2/nifty50/5m/manifest.json` | 49 | `TATAMOTORS` (`count = 0`) |

Exact 49-symbol list (manifest order, not invented):

```
ADANIENT, ADANIPORTS, APOLLOHOSP, ASIANPAINT, AXISBANK, BAJAJ-AUTO, BAJFINANCE, BAJAJFINSV, BEL, BHARTIARTL, BPCL, BRITANNIA, CIPLA, COALINDIA, DRREDDY, EICHERMOT, GRASIM, HCLTECH, HDFCBANK, HDFCLIFE, HEROMOTOCO, HINDALCO, HINDUNILVR, ICICIBANK, INDUSINDBK, INFY, ITC, JSWSTEEL, KOTAKBANK, LT, M&M, MARUTI, NESTLEIND, NTPC, ONGC, POWERGRID, RELIANCE, SBILIFE, SBIN, SHRIRAMFIN, SUNPHARMA, TATACONSUM, TATASTEEL, TCS, TECHM, TITAN, TRENT, ULTRACEMCO, WIPRO
```

Rules for later ingestion (not implemented here):

- Normalize incoming tickers by strip + uppercase.
- Document NSE suffixes (for example `.NS`) may be stripped.
- Do **not** manually map unknown names at train time.
- Unmapped symbols are discarded.
- Do **not** substitute another company for `TATAMOTORS`.
- `BAJAJ-AUTO` and `M&M` must survive as those exact strings after normalization.

## 3. Required date window

H001 event coverage filter:

- `available_at >= 2024-01-01`
- `available_at <= 2025-12-31`
- all timestamps timezone-aware

A provider may hold rows outside this window. Only this window matters for the audit. This is **not** a request for three years of market bars.

## 4. Required event fields

Minimum fields to evaluate per source:

| Field | Role |
|---|---|
| `symbol` | Must map onto the 49 manifest strings |
| `event_type` | Earnings / results / material corporate event |
| `announced_at` | Company/exchange announcement clock, if any |
| `published_at` | Publication clock, if distinct |
| `available_at` | First time a backtest may observe the fact |
| `source` | Provenance |
| `source_id` | Stable filing/announcement id |
| `period_end` | Fiscal period end; **never** treated as `available_at` |
| event/value fields | EPS, profit, revenue, guidance, etc. |
| revision/version | Original vs restated / revised rows |

These are **not automatically equivalent**: announcement date, publication date, period end, retrieval time, database update time, market availability time.

## 5. Candidate sources

### Source

- **Name:** NSE India corporate announcements, financial results, and announcement XBRL
- **URL/documentation:**
  - https://www.nseindia.com/companies-listing/corporate-filings-announcements
  - https://www.nseindia.com/companies-listing/corporate-filings-financial-results
  - https://www.nseindia.com/companies-listing/corporate-filings-announcements-xbrl
  - https://www.nseindia.com/static/companies-listing/xbrl-information
  - Unofficial but widely observed JSON: `https://www.nseindia.com/api/corporate-announcements?index=equities&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY&symbol={SYMBOL}`
- **Provider:** National Stock Exchange of India (official disclosure system / NEAPS)
- **Data type:** Regulatory corporate announcements (PDF + text), financial-results tables, XBRL/iXBRL instance documents
- **Coverage:** All NSE listed equities, including the 49 snapshot names. Historical queries exist by symbol and date range. NIFTY50 names file quarterly/annual results under SEBI LODR.
- **Cost/access:** Public website; no commercial API contract. Access is cookie/session gated, rate-limited in practice, and not a licensed bulk feed. Third-party wrappers (for example Apify `foxlabs/india-listed-company-filings`) scrape the same NSE JSON and charge per row; they are an **access layer**, not an independent timestamp authority.
- **API/file availability:** JSON endpoints behind the public site; PDF/XBRL on `nsearchives.nseindia.com`. Not a SLA-backed historical product.

#### Timestamp fields

- **available timestamp (candidate):** Exchange Dissemination Time / `disseminatedAt` on announcement XBRL pages (`BROADCAST DATE/TIME` vs `Exchange Dissemination Time`, usually IST wall-clock to the second).
- **publication timestamp:** Broadcast / `announcementAt` / `broadcastdate` / `re_broadcast_timestamp` on financial-results rows (company filing / NSE broadcast of the results record).
- **announcement timestamp:** Same family as broadcast time; subject/category identifies the event (financial results, board outcome, etc.).
- **retrieval timestamp:** Whatever clock a scraper uses when it hits NSE. **Not** in the exchange record.
- **revision timestamp:** Separate later announcement with filing status `revised` / category such as results correction; `re_broadcast_timestamp` on results rows. NSE XBRL Q&A distinguishes Original vs Revision submissions.

#### Timestamp semantics

- **period_end / `to_date`:** Fiscal quarter or year end. Generated by the issuer’s reporting calendar. Not market availability.
- **BROADCAST DATE/TIME / `announcementAt`:** NSE’s recorded time the disclosure was broadcast on the exchange system. Clock is exchange/IST. Historical if the archive preserves the original field (must be verified on a sample, not assumed). This is the company’s filing hitting NSE’s announcement bus, not a researcher’s download time.
- **Exchange Dissemination Time / `disseminatedAt`:** NSE’s recorded time the announcement was disseminated to the market feed. Typically equal to broadcast plus 0–2 seconds on current UI samples. This is the **strongest documented proxy** for first public availability on NSE. It is still an **exchange dissemination clock**, not a reconstructed NBBO print time, and it is **not** proven in this audit to be immutable for 2024–2025 rows.
- **`filedAt` on financial-results feeds:** Filing time of the results/XBRL package (IST). After 1 Apr 2025, NSE circulars require Integrated Filing–Financial XBRL on the **same date** as the PDF results; earlier, XBRL could lag PDF by up to 24 hours. Therefore **XBRL `filedAt` can be later than PDF dissemination** and must not be blindly used as `available_at` for 2024 rows.
- **`re_broadcast_timestamp`:** Timestamp attached to the results table row; used when results are re-broadcast / revised. Semantics are “NSE results-record broadcast,” not period end.
- **Scraper `scraped_at` / `retrieved_at`:** Generated at crawl time. Unsuitable as `available_at`.

#### Point-in-time capability

**UNCERTAIN** (closest to YES among free/official sources).

Exchange dissemination timestamps, if historically preserved per announcement id, can support an as-of backtest (`available_at <= as_of`). This audit did **not** pull the 49-name 2024–2025 extract, so immutability, completeness, timezone tagging, and PDF-vs-XBRL lag are unproven. Do **not** invent `available_at = announced_at + 2 hours`.

#### Revision support

**PARTIAL / UNCERTAIN.**

NSE records Original vs Revision on XBRL submissions and exposes later “results correction” / revised financial-result rows with their own broadcast times. A dataset that **keeps every announcement row** can reconstruct T1 vs T2. A dataset that **overwrites** the results table with the latest XBRL numbers cannot. Public UI does not document a full versioned value history inside a single `source_id`.

#### 49-symbol coverage

**YES** (listed NSE names; `TATAMOTORS` is out of universe by snapshot, not by NSE).

#### 2024-2025 coverage

**YES** expected for quarterly/annual results of large caps; **not empirically counted** in this discovery pass.

#### Verdict

**POSSIBLY SUITABLE** — strongest official candidate. Not PIT-ready until Developer 2 verifies historical dissemination timestamps and revision rows on an acquired extract.

---

### Source

- **Name:** BSE corporate announcements
- **URL/documentation:**
  - https://www.bseindia.com/corporates/ann.html
  - `https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w`
- **Provider:** BSE Limited
- **Data type:** Corporate announcements (PDF + metadata), including financial results / board outcomes
- **Coverage:** BSE-listed names. The 49 snapshot symbols are dual-listed large caps in practice; mapping requires BSE **scrip codes**, not NSE strings.
- **Cost/access:** Public website JSON; unofficial, header/Referer gated, paginated.
- **API/file availability:** JSON `Table` rows; attachments on BSE.

#### Timestamp fields

Documented UI/API fields include:

- `NEWS_DT` / `DT_TM` — announcement datetime shown on BSE
- `News_submission_dt` — **Exchange Received Time**
- `DissemDT` — **Exchange Disseminated Time**
- `TimeDiff` — received-to-disseminated lag
- scraper retrieval time — not in the exchange payload

#### Timestamp semantics

- **`News_submission_dt`:** When BSE received the filing. Exchange clock, IST formatting in the public UI. Not necessarily when the market saw it.
- **`DissemDT`:** When BSE disseminated the announcement. Closest BSE analogue of NSE Exchange Dissemination Time. Candidate `available_at` **if** historically stored and timezone-aware.
- **`NEWS_DT`:** Display/announcement datetime; community dumps treat it as the news datetime. Must not be assumed identical to `DissemDT`.
- **period_end:** Not this feed’s primary key; results PDFs contain period end separately.

#### Point-in-time capability

**UNCERTAIN.** Same class as NSE: exchange dissemination clock is the right *kind* of timestamp, but historical immutability and complete 2024–2025 coverage for all 49 scrip codes are unverified. Dual-exchange names can disseminate on NSE and BSE at slightly different times; using the **earlier** of the two disseminations is a later design choice, not something to invent now.

#### Revision support

**UNCERTAIN.** New announcement rows can represent updates; there is no documented value-level version graph. Overwrite risk if only the latest PDF is kept.

#### 49-symbol coverage

**YES** after scrip-code mapping for these large caps; **PARTIAL** until a deterministic NSE-symbol → BSE-scrip table is audited. Unmapped codes must be discarded, not hand-mapped at train time.

#### 2024-2025 coverage

**YES** expected; not counted here.

#### Verdict

**POSSIBLY SUITABLE** as corroboration of NSE dissemination times, not as a substitute universe definition (H001 symbols are NSE snapshot strings).

---

### Source

- **Name:** CMIE Prowess / ProwessDx
- **URL/documentation:**
  - https://www.cmie.com/ (ProwessDx product pages)
  - https://prowessdx.cmie.com/ (vintage announcements)
- **Provider:** Centre for Monitoring Indian Economy (CMIE)
- **Data type:** Standardized annual and interim financials, identity, corporate actions, prices; academic bulk download (ProwessDx vintages)
- **Coverage:** Tens of thousands of Indian companies, listed and unlisted, time series from ~1990. NIFTY50 coverage is expected.
- **Cost/access:** Institutional / academic subscription. ProwessDx is for educational and not-for-profit research organisations, not a free API.
- **API/file availability:** Delimited text downloads from frozen **vintages** (March / September / December snapshots). Contents of a vintage are not changed after release.

#### Timestamp fields

- Vintage **as-of date** (for example 31 Mar 2025) and **CMIE release announcement date** (for example 1 Apr 2025)
- Financial **period end**
- Some Prowess modules expose announcement/event dates for actions; public marketing pages do **not** document an exchange dissemination timestamp to the second

#### Timestamp semantics

- **Vintage date:** When CMIE froze the database snapshot. This is a **vendor publication calendar** (quarterly-ish), not the moment EPS hit NSE.
- **CMIE announcement of a vintage:** When subscribers could download that vintage. Using this as `available_at` would delay every 2024–2025 earnings event until the next CMIE freeze — too coarse for an event study, and **not** market availability.
- **Period end:** Fiscal period. Forbidden as `available_at`.
- **Company announcement date inside Prowess (if present in licensed tables):** Typically a date, not proven here to be exchange dissemination time.

#### Point-in-time capability

**NO** for H001’s event-level `available_at`.

Vintage PIT is real **for CMIE’s own database state** (what a researcher downloading the March 2025 vintage would have seen in Prowess). That is not “when the market first saw the result.” Cross-vintage comparison can show restatements of financial statements at vendor frequency, not tick-level first print.

#### Revision support

**PARTIAL.** Frozen vintages do not mutate; comparing two vintages can show later restatements. Intra-vintage event revisions with exchange clocks are not what the product is.

#### 49-symbol coverage

**YES** expected (listed large caps).

#### 2024-2025 coverage

**YES** for financial statement values; **NO** as event-availability timestamps for the H001 window.

#### Verdict

**NOT SUITABLE** as the H001 `available_at` authority. Useful later as a values cross-check against NSE XBRL, not as the availability clock.

---

### Source

- **Name:** ACE Equity Nxt (Accord Fintech)
- **URL/documentation:**
  - https://www.aceequitynxt.com/
  - https://www.accordfintech.com/ace-equity-nxt
- **Provider:** Accord Fintech Pvt Ltd
- **Data type:** Listed/private company financials, quarterly results, corporate actions, digital copies of results/annual reports, live news
- **Coverage:** ~7,000 listed + many private Indian companies. NIFTY50 expected.
- **Cost/access:** Commercial Windows/cloud application; institutional licence. Not a documented public historical events API.
- **API/file availability:** Application export / digital reports. No public PIT schema.

#### Timestamp fields

Public pages emphasize **results and annual reports** and **live news**. They do not document `DissemDT`-class fields, version ids, or first-print availability.

#### Timestamp semantics

Unknown without a licensed data dictionary. Typical Indian desktop databases store **result date** (calendar day of announcement) alongside **period end**. That is not sufficient. Retrieval/update time inside the app is a vendor clock.

#### Point-in-time capability

**UNCERTAIN**, treated as **NO** until Accord provides a written definition that a field is exchange first-dissemination time and is not overwritten on restatement.

#### Revision support

**UNCERTAIN.** Linking line items to the annual report does not equal keeping the first-released quarterly EPS.

#### 49-symbol coverage

**YES** expected.

#### 2024-2025 coverage

**YES** expected for values; timestamp quality unknown.

#### Verdict

**NOT SUITABLE** on current public evidence (date ≠ availability). Re-open only if Accord delivers a field dictionary that survives Developer 2’s timestamp audit.

---

### Source

- **Name:** LSEG I/B/E/S actuals / history (WRDS and QFS)
- **URL/documentation:**
  - I/B/E/S QFS user guide (Expanded Actuals: announce date/time vs activation date/time)
  - I/B/E/S Detail History (restated actuals files)
- **Provider:** LSEG (formerly Refinitiv / Thomson Reuters)
- **Data type:** Analyst estimates, reported actuals, surprises; India coverage exists for large caps but is estimate-centric
- **Coverage:** Global, including many NSE names. Exact 49/49 not verified in this pass.
- **Cost/access:** Expensive institutional / WRDS. Not being purchased here.
- **API/file availability:** QFS files, history packages, some LSEG APIs.

#### Timestamp fields

- **Announce date / announce time:** “exact date the company has reported”; **QFS states announce times may not always represent the time of the company’s official announcement**
- **Activation date/time:** when the actual was **entered into the Refinitiv database** (vendor clock)
- Restated-actuals files: subsequent restatement rows

#### Timestamp semantics

- **Announce date:** Vendor’s interpretation of report date. Date-level may be usable; time-of-day is explicitly unreliable per QFS.
- **Activation time:** Vendor ingestion, **not** market availability. Using it as `available_at` would leak future vendor processing delay in the wrong direction or delay the backtest arbitrarily.
- **Go-forward actuals:** Accounting-basis alignment for the *next* period; can rewrite the stored “actual” without being a new public print.

#### Point-in-time capability

**NO** as exchange-grade `available_at`. Announce *date* plus a conservative next-session rule would still be an **invention**, which this audit forbids unless the provider defines it.

#### Revision support

**YES** at vendor level (restated actuals files; go-forward vs reported). That reconstructs I/B/E/S history, not NSE tape history.

#### 49-symbol coverage

**UNCERTAIN / likely YES** for large NIFTY names; must be counted after a licence, not assumed.

#### 2024-2025 coverage

**YES** expected for actuals dates.

#### Verdict

**NOT SUITABLE** as the primary H001 availability clock. Optional later overlay for consensus/surprise, not for `available_at`.

---

### Source

- **Name:** FactSet Estimates / FactSet Point-in-Time estimates
- **URL/documentation:** FactSet Estimates On Demand; FactSet PIT estimates white paper (`FE_PIT_*`)
- **Provider:** FactSet
- **Data type:** Estimates, broker actuals, consensus snapshots as of local midnight
- **Coverage:** Global institutional; India large-cap likely. 49/49 uncounted.
- **Cost/access:** Institutional. Not purchased.
- **API/file availability:** Workstation / API; PIT consensus is **daily local-midnight snapshots of consensus**, not exchange dissemination of results.

#### Timestamp fields

- Actuals collection timestamp / report date
- PIT consensus as-of date (local market midnight)
- Broker estimate revision times (estimates, not issuer actuals)

#### Timestamp semantics

FactSet documents collecting US/EU/JP actuals from newswires as they appear; India is **not** in that listed newswire list in the Estimates On Demand PDF reviewed here. PIT database = consensus as of midnight, updated in regional batches. That is PIT for **analyst consensus**, not for **issuer earnings print**.

#### Point-in-time capability

**NO** for issuer `available_at`. **YES** for consensus-as-of-midnight if that were the H001 feature (it is not).

#### Revision support

**YES** for estimates PIT; actuals restatement behaviour needs a licensed dictionary.

#### 49-symbol coverage

**UNCERTAIN.**

#### 2024-2025 coverage

**YES** expected for estimates.

#### Verdict

**NOT SUITABLE** for H001 earnings availability.

---

### Source

- **Name:** EODHD earnings calendar API
- **URL/documentation:** https://eodhd.com/financial-apis/calendar-upcoming-earnings-ipos-and-splits
- **Provider:** EOD Historical Data
- **Data type:** Earnings calendar (`report_date`, fiscal `date`, `actual`, `estimate`, `before_after_market`)
- **Coverage:** Global including `.NS` tickers. Completeness for all 49 in 2024–2025 not verified.
- **Cost/access:** Paid API; free/low tiers limited. Not purchased.
- **API/file availability:** `GET /api/calendar/earnings`

#### Timestamp fields

- `date` — fiscal period end
- `report_date` — announcement **calendar date**
- `before_after_market` — session label (Before/After), often US-centric
- no exchange dissemination datetime documented

#### Timestamp semantics

`report_date` is a **date**, not a first-print timestamp. `before_after_market` is a coarse session flag, not IST dissemination. `date` is period end. Latest `actual` is the current stored EPS.

#### Point-in-time capability

**NO.**

#### Revision support

**NO** (latest actual/estimate; no version file documented).

#### 49-symbol coverage

**PARTIAL** until a symbol-by-symbol pull; `.NS` naming still needs deterministic mapping (`BAJAJ-AUTO`, `M&M`).

#### 2024-2025 coverage

**PARTIAL / UNCERTAIN.**

#### Verdict

**NOT SUITABLE.**

---

### Source

- **Name:** Financial Modeling Prep earnings calendar
- **URL/documentation:** https://site.financialmodelingprep.com/developer/docs/stable/earnings-calendar
- **Provider:** Financial Modeling Prep
- **Data type:** Earnings calendar (date, estimated/actual EPS, optional estimated report time / BMO-AMC)
- **Coverage:** Stronger for US; NSE via `.NS` fundamentals endpoints exist. 49/49 calendar completeness unknown.
- **Cost/access:** Paid API. Not purchased.
- **API/file availability:** `/stable/earnings-calendar`, historical per-symbol calendar

#### Timestamp fields

- `date` — report/announcement **date**
- `time` / session — estimated window; FMP states this is **not a guaranteed exact timestamp**
- `fiscalDateEnding` / `periodEnding` — period end
- `updatedFromDate` — provider update date (vendor clock)

#### Timestamp semantics

Announcement **date** plus an estimated session is not NSE dissemination. `updatedFromDate` is when FMP updated the row. Actuals may be revised in place.

#### Point-in-time capability

**NO.**

#### Revision support

**NO** (latest calendar row).

#### 49-symbol coverage

**PARTIAL / UNCERTAIN.**

#### 2024-2025 coverage

**PARTIAL / UNCERTAIN.**

#### Verdict

**NOT SUITABLE.**

---

### Source

- **Name:** Yahoo Finance / Investing.com / similar retail calendars
- **URL/documentation:** Yahoo quote financials; retail earnings tables
- **Provider:** Yahoo, Fusion Media, etc.
- **Data type:** Quarterly EPS/revenue tables keyed by period or by a **release date**
- **Coverage:** Large NIFTY names appear; quality and timezone are uncontrolled
- **Cost/access:** Public pages / unofficial APIs
- **API/file availability:** Scraping / unofficial JSON; ToS constrained

#### Timestamp fields

Release **date** (calendar day). Period end on financial statements. No exchange dissemination time.

#### Timestamp semantics

Retail “earnings date” is often estimated, timezone-naive, and updated after the fact. Period-end columns are fiscal, not availability.

#### Point-in-time capability

**NO.**

#### Revision support

**NO.**

#### 49-symbol coverage

**PARTIAL.**

#### 2024-2025 coverage

**PARTIAL.**

#### Verdict

**NOT SUITABLE.**

---

### Source

- **Name:** Repository fixtures and Intelligence RSS retrieval
- **URL/documentation:** `packages/contracts/src/contracts/fixtures.py`; Intelligence news store (`published_at`, `retrieved_at`)
- **Provider:** This repository (synthetic) / RSS fetches
- **Data type:** Hand-written EPS rows; news articles

#### Timestamp fields

- Fixture `announced_at` / `available_at` — **authored for tests**, `metadata.fixture = true`
- News `published_at` — feed-declared publish time
- News `retrieved_at` — crawler clock

#### Timestamp semantics

Fixtures are not historical. `retrieved_at` is when our process saw the item, not when the market did. RSS `published_at` is not an exchange dissemination clock and is not revision-aware.

#### Point-in-time capability

**NO.**

#### Revision support

**NO.**

#### 49-symbol coverage

**NO** (five fixture names only).

#### 2024-2025 coverage

**NO.**

#### Verdict

**NOT SUITABLE.** Explicitly out of scope as H001 evidence.

---

## 6. Recommended source

**Strongest candidate:** **NSE India corporate announcements + financial-results / XBRL archive**, using **Exchange Dissemination Time** (fallback: broadcast time if dissemination is missing on a given row) as the *candidate* `available_at`, with **BSE `DissemDT` as a cross-check** on dual-listed names.

This is **not PIT-ready**. Evidence supports only:

- the **right kind** of timestamp exists on the official disclosure systems (dissemination / broadcast in IST, to the second)
- the **right universe** is listed on NSE
- **original vs revised** filing flags exist, if every row is stored

It does **not** yet prove:

- every one of the 49 names has a complete 2024–2025 results series with those timestamps intact
- timestamps are immutable in the public archive
- PDF board-outcome time vs later XBRL time is handled without lookahead
- values (EPS etc.) can be joined to the first-print row rather than the latest restatement

Do **not** call this PIT-ready. Do **not** buy CMIE/FactSet/I/B/E/S for `available_at`. Do **not** derive availability from period end or RSS `retrieved_at`.

**Task 3 note:** a freeze of NSE corporate announcements for the 49 snapshot names (2024–2025 window) was later stored under gitignored `datasets/` (`h001-nse-raw-20261010T140237Z`). Acquisition of that freeze does **not** complete items below. Exchange Dissemination Time remains a **candidate proxy**, not proven first-public availability.

## 7. Exact remaining blocker

A candidate extract **has been acquired**. H001 stays **event-data blocked** because Gate 2 did **not** prove timestamp semantics, archive immutability, 49×quarter results coverage, integrity-hash reproducibility, or restatement-safe values. The Gate 2 `DATA READY` conclusion is withdrawn.

Remaining work (still not modelling; see also readiness §14–§18):

1. ~~Pull NSE announcements for the exact 49 symbols and 2024–2025 window.~~ **Done as a freeze** (not recertified here). Financial-results/XBRL vintage and 2023-Q4/2026-Q1 censoring buffers remain open if Scope B or period-print completeness is required.
2. Persist **raw rows** (do not overwrite). Keep `source_id` / announcement id, subject, PDF URL, XBRL URL, broadcast time, dissemination time, period end, original vs revised. Freeze exists; restatement **values** still missing.
3. Timestamp audit on the extract (still required):
   - Are broadcast/dissemination fields present on ≥ required earnings events?
   - Timezone: store as aware `Asia/Kolkata` (or offset `+05:30`), never naive. IST tagging in the freeze is a **convention**, not verified vendor metadata.
   - Does a later revision **change** the original row’s timestamps/values in the live API, or only add a new row? **Unresolved.**
   - PDF vs XBRL lag for 2024 (up to 24h) vs 2025 (same-day XBRL). **Unresolved.**
4. Coverage table: 49 × quarters in 2024–2025; missing events listed, not imputed. **Not produced.** Proposed classifier and table spec live in readiness §§15–16; do not run them without authorization.
5. Define `available_at` **from provider fields** (candidate: dissemination / `exchdisstime`, else broadcast) **only after** authoritative semantics or an approved limitation. **No +2 hour rule.**
6. Reproducible artifact-integrity recipe (historical digest `b0f4760f…` is UNVERIFIED). Only after the above can H001 move toward `DATA READY`. Until then:

`DATA NOT READY`  
`EVENT_DATA_BLOCKED`  
`H001 = BLOCKED_PRECONDITION`  
`READY_TO_RUN = NO`
