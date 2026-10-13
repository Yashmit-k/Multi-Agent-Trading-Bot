# H001 timestamp and leakage (sprint note)

`DATA NOT READY` · `DATA_PREP_READY = NO` · `READY_TO_RUN = NO`

Measured on freeze `h001-nse-raw-20261010T140237Z` (18,235 in-universe rows): field `exchdatetime` **does not exist**. Availability uses `exchdisstime` only. See `h001-timestamp-provenance.json`.

- `exchdisstime` is an offset-naive `DD-MMM-YYYY HH:MM:SS` string. This repo tags it `Asia/Kolkata`. That is a **convention**, not NSE schema.
- It is **not** proven first publicly actionable time. Historical immutability of JSON fields is **not** proven.
- Do **not** use later XBRL / `filedAt` as first print (2024 PDF-to-XBRL lag up to 24h; NSE/CML/2025/20 same-date XBRL still later than the PDF announcement).
- Joins must use `available_at` / `exchdisstime` **<=** decision `as_of`. Candle snapshot `nifty50_1d_20261005` (`candle_sha256` `0411a895…`) covers bars from 2024-01-01 UTC session open for names with `count>0`. Holdout was not accessed.
- v2 board-meeting filter uses attachment text at freeze time; that text is source-backed but not an official subject enum.

No labels were generated, so session-level leakage of features was not executed.
