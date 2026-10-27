# Global markets and NIFTY: pre-registered protocol

Status: **PRE-REGISTERED 2026-10-27, before any global series was compared with Indian returns.** The only work done beforehand was one download test (S&P 500 daily bars, 2015-01-02 to 2026-10-26).

Question: does what happened in world markets **before 09:15 IST** predict NIFTY 50 returns **after the open**, the part a trade entered near the open can actually capture?

The opening gap is measured too, as a sanity check: it should be predicted, but it is already in the open price.

## Data

- **Global inputs:** Yahoo Finance daily bars via the public chart endpoint, fetched 2026-10-27 into `datasets/research/global_markets/` (gitignored), 2015-01-01 onward:

  | Input | Yahoo symbols |
  |---|---|
  | US equities | S&P 500 `^GSPC`, Nasdaq `^IXIC` |
  | US fear index | VIX `^VIX` |
  | Asia | Nikkei `^N225`, Kospi `^KS11`, Hang Seng `^HSI` |
  | Europe | FTSE `^FTSE`, DAX `^GDAXI` |
  | Macro | Brent `BZ=F`, USD/INR `INR=X`, dollar index `DX-Y.NYB`, US 10-year yield `^TNX` |

- **NIFTY 50:** daily bars from `datasets/research/dip_history/daily_2015_2026.jsonl` (to 2026-10-05).

## Timing (what is known before 09:15 IST on Indian session D)

| Input | Value used for D | Why it is known |
|---|---|---|
| US, VIX, yields, dollar, Brent, USD/INR | return of the latest bar whose exchange-local date is before D (close vs previous close) | the US closes by 02:30 IST |
| Europe | the same rule | closes by 22:00 IST on D−1. Reported only, because it overlaps India's own afternoon |
| Asia | **the gap only**: the open of D vs the close of the previous Asian session | Tokyo and Seoul open 05:30 IST, Hong Kong 06:45 IST. Asia's close of D is **not** used: it comes after 09:15 |

A day with no new bar for an input (a foreign holiday) gives that input a value of 0.

## Composite score (fixed here; nothing is fitted)

Each input is divided by its own standard deviation over the previous 250 Indian sessions (known at the time) and given a sign so that "good for risk" is positive:
- `+` S&P 500, Nasdaq, and the Asia gap (the mean of Nikkei, Kospi and Hang Seng);
- `−` the VIX change, Brent, USD/INR (rupee weakening), the dollar index and the US 10-year yield change.

**Composite** = the equal-weight mean of those eight scaled inputs. Europe is excluded.

## Targets (NIFTY 50)

- **Gap** (sanity check): open of D vs the close of D−1.
- **Open to close** (main): close of D vs the open of D.
- **Open to 5 days** (main): close of D+4 vs the open of D.

## Measures, per period

| Period | Dates |
|---|---|
| Train | 2015-03-01 to 2020-12-31 |
| Validate | 2021-01-01 to 2023-12-31 |
| Test | 2024-01-01 to 2026-10-05 |

- Spearman correlation of each input and of the composite with each target.
- Mean NIFTY open-to-close and open-to-5-day return on **global risk-off days** (composite in its bottom 20%, using thresholds from the previous 250 sessions only) vs all other days, in basis points.
- A 90% block bootstrap interval (calendar-month blocks, 2,000 draws) of the pooled composite correlation.

## Gate (composite, for each main target separately)

The composite is **useful** for a target only if both hold:
1. Its correlation has the **same sign** in train, validate and test.
2. The pooled 90% bootstrap interval excludes zero.

If it is useful for open to 5 days or open to close, the next step is a separate decision on how the live agent may use it (e.g. size on risk-off days). If not, the agent stays observe-only and its view is context, not a trading input.

The gap result is reported but never counts toward the gate.

## Output

- `services/quant/docs/results/global-markets-result.json`;
- `services/quant/docs/global-markets-result.md`.

Run:

```
python -m quant_agents.research.global_markets
```
