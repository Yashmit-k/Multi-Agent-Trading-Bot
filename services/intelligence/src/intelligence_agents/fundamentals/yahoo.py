"""Nightly fundamentals fetch from Yahoo Finance (unofficial feed, via yfinance) into fundamentals.csv.

Writes, per NSE symbol, point-in-time rows for the Fundamental, Valuation and Earnings agents:

  eps             trailing-twelve-month EPS in INR (Yahoo `trailingEps`, quoted in the trading currency)
  pe_at_fetch     trailing P/E at fetch time (information; Valuation recomputes P/E from the live price)
  peer_median_pe  median trailing P/E of the stock's NIFTY 50 peers, never the stock itself: its Yahoo industry
                  when that has >= 3 other members, else its Yahoo sector (>= 3 others), else all the others
  peer_count      how many peers stand behind peer_median_pe
  profit_growth   year-on-year quarterly earnings growth, fraction
  revenue_growth  year-on-year quarterly revenue growth, fraction
  margin          trailing net profit margin, fraction
  roe             return on equity, fraction (Yahoo's figure, else TTM net income / latest equity)
  debt_to_equity  total debt / equity, fraction (absent for banks and insurers)

Point-in-time rule: Yahoo does not say when a result was announced, so `announced_at` and
`available_at` are both the fetch time. Rows are keyed by symbol, quarter and metric; a value
already in the file is never rewritten (a revised value gets a new row with a later available_at).
That is honest for live use and means these rows must not be used to backtest the past.
Stale data (latest quarter older than MAX_QUARTER_AGE_DAYS) is skipped.
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import statistics
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterable

logger = logging.getLogger(__name__)

SOURCE = "yahoo-finance"
FIELDS = ["symbol", "metric", "value", "unit", "period", "announced_at", "available_at", "source", "source_id"]
MAX_QUARTER_AGE_DAYS = 200
MIN_PEERS = 3
# NSE symbol -> Yahoo ticker when it is not simply "<symbol>.NS".
YAHOO_TICKER: dict[str, str] = {}


@dataclass(frozen=True)
class Snapshot:
    symbol: str
    sector: str | None
    quarter_end: date | None
    eps: float | None
    pe: float | None
    profit_growth: float | None
    revenue_growth: float | None
    margin: float | None
    roe: float | None
    debt_to_equity: float | None
    industry: str | None = None


def _num(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def quarter_label(day: date) -> str:
    return f"{day.year}Q{(day.month - 1) // 3 + 1}"


def snapshot_from_info(symbol: str, info: dict, statement_roe: float | None = None) -> Snapshot:
    """Map Yahoo `info` fields to our metrics. Yahoo's debtToEquity is a percentage; ours is a fraction."""
    recent = _num(info.get("mostRecentQuarter"))
    quarter_end = datetime.fromtimestamp(recent, tz=timezone.utc).date() if recent else None
    de = _num(info.get("debtToEquity"))
    return Snapshot(
        symbol=symbol,
        sector=info.get("sector") or None,
        quarter_end=quarter_end,
        eps=_num(info.get("trailingEps")),
        pe=_num(info.get("trailingPE")),
        profit_growth=_num(info.get("earningsQuarterlyGrowth")),
        revenue_growth=_num(info.get("revenueGrowth")),
        margin=_num(info.get("profitMargins")),
        roe=_num(info.get("returnOnEquity")) if _num(info.get("returnOnEquity")) is not None else statement_roe,
        debt_to_equity=None if de is None else de / 100,
        industry=info.get("industry") or None,
    )


@dataclass(frozen=True)
class PeerGroup:
    median_pe: float
    count: int
    basis: str  # "industry", "sector" or "all"


def peer_groups(snapshots: Iterable[Snapshot]) -> dict[str, PeerGroup]:
    """Median positive trailing P/E of each stock's peers, the stock itself excluded.

    Yahoo's industry is preferred when it holds at least MIN_PEERS other NIFTY 50 members (its sectors are broad:
    RELIANCE sits with PSU energy names), then the sector, then every other stock with a positive P/E.
    """
    items = [item for item in snapshots if item.pe is not None and item.pe > 0]
    out: dict[str, PeerGroup] = {}
    for item in items:
        others = [other for other in items if other.symbol != item.symbol]
        for basis in ("industry", "sector"):
            label = getattr(item, basis)
            peers = [other.pe for other in others if label and getattr(other, basis) == label]
            if len(peers) >= MIN_PEERS:
                break
        else:
            basis, peers = "all", [other.pe for other in others]
        if peers:
            out[item.symbol] = PeerGroup(statistics.median(peers), len(peers), basis)  # type: ignore[arg-type]
    return out


def peer_medians(snapshots: Iterable[Snapshot]) -> dict[str, float]:
    return {symbol: group.median_pe for symbol, group in peer_groups(snapshots).items()}


def older_quarter_count(snapshots: Iterable[Snapshot], today: date) -> tuple[int, str | None]:
    """Stocks whose latest dated, non-stale quarter is behind the newest one in the batch (results season)."""
    labels = [quarter_label(item.quarter_end) for item in snapshots if item.quarter_end is not None and (today - item.quarter_end).days <= MAX_QUARTER_AGE_DAYS]
    if not labels:
        return 0, None
    newest = max(labels)
    return sum(1 for label in labels if label != newest), newest


RANKED = (("profit_growth", True), ("revenue_growth", True), ("roe", True), ("debt_to_equity", False))


def percentile_ranks(snapshots: Iterable[Snapshot]) -> dict[str, dict[str, float]]:
    """symbol -> {rank_<metric>: 0..1}, 1 = best of the NIFTY 50 on that metric (lower debt is better)."""
    items = list(snapshots)
    out: dict[str, dict[str, float]] = {item.symbol: {} for item in items}
    for metric, higher_is_better in RANKED:
        present = [(item.symbol, getattr(item, metric)) for item in items if getattr(item, metric) is not None]
        if len(present) < 5:
            continue
        ordered = sorted(present, key=lambda pair: pair[1], reverse=not higher_is_better)  # worst first
        for position, (symbol, _) in enumerate(ordered):
            out[symbol][f"rank_{metric}"] = position / (len(ordered) - 1)
    return out


def rows_for(
    snapshot: Snapshot,
    peer_pe: float | None,
    fetched_at: datetime,
    today: date,
    ranks: dict[str, float] | None = None,
    peer_count: int | None = None,
) -> list[dict[str, str]]:
    if snapshot.quarter_end is None or (today - snapshot.quarter_end).days > MAX_QUARTER_AGE_DAYS:
        return []  # stale or undated: better no row than an old one presented as current
    period = quarter_label(snapshot.quarter_end)
    stamp = fetched_at.astimezone(timezone.utc).isoformat()
    values: list[tuple[str, float | None, str, str]] = [
        ("eps", snapshot.eps, "INR", period),
        ("pe_at_fetch", snapshot.pe, "ratio", today.isoformat()),
        ("peer_median_pe", peer_pe, "ratio", today.isoformat()),
        ("peer_count", peer_count, "count", today.isoformat()),
        ("profit_growth", snapshot.profit_growth, "ratio", period),
        ("revenue_growth", snapshot.revenue_growth, "ratio", period),
        ("margin", snapshot.margin, "ratio", period),
        ("roe", snapshot.roe, "ratio", period),
        ("debt_to_equity", snapshot.debt_to_equity, "ratio", period),
    ] + [(name, value, "ratio", today.isoformat()) for name, value in sorted((ranks or {}).items())]
    rows = []
    for metric, value, unit, label in values:
        if value is None:
            continue
        rows.append(
            {
                "symbol": snapshot.symbol,
                "metric": metric,
                "value": str(Decimal(str(round(value, 6)))),
                "unit": unit,
                "period": label,
                "announced_at": stamp,
                "available_at": stamp,
                "source": SOURCE,
                "source_id": f"{snapshot.symbol}-{label}-{metric}",
            }
        )
    return rows


def merge(existing: list[dict[str, str]], new: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    """Append new rows; never rewrite one already present. A changed value is kept as a dated revision."""
    latest: dict[str, dict[str, str]] = {}
    for row in existing:
        base = row["source_id"].split("~rev")[0]
        latest[base] = row
    added = []
    for row in new:
        previous = latest.get(row["source_id"])
        if previous is None:
            added.append(row)
        elif Decimal(previous["value"]) != Decimal(row["value"]):
            added.append({**row, "source_id": f"{row['source_id']}~rev{row['available_at'][:10]}"})
    # A same-day revision can only be added once.
    seen = {row["source_id"] for row in existing}
    added = [row for row in added if row["source_id"] not in seen]
    return existing + added, len(added)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    tmp = path.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({key: row.get(key, "") for key in FIELDS} for row in rows)
    tmp.replace(path)


def _statement_roe(ticker) -> float | None:  # type: ignore[no-untyped-def]
    """TTM net income / latest stockholders' equity from the quarterly statements, when Yahoo has 4 quarters."""
    try:
        income, balance = ticker.quarterly_income_stmt, ticker.quarterly_balance_sheet
        income_row = next(name for name in ("Net Income Common Stockholders", "Net Income") if name in income.index)
        equity_row = next(name for name in ("Stockholders Equity", "Common Stock Equity") if name in balance.index)
        quarters = [value for value in income.loc[income_row].tolist()[:4] if _num(value) is not None]
        equity = _num(balance.loc[equity_row].tolist()[0])
        if len(quarters) == 4 and equity and equity > 0:
            return sum(quarters) / equity
    except Exception:  # noqa: BLE001 - optional fallback only
        return None
    return None


def fetch_snapshots(symbols: list[str], *, pause: float = 0.3, factory: Callable | None = None) -> list[Snapshot]:
    if factory is None:
        import yfinance as yf

        factory = yf.Ticker
    out = []
    for symbol in symbols:
        ticker = factory(YAHOO_TICKER.get(symbol, f"{symbol}.NS"))
        try:
            info = ticker.info or {}
        except Exception as exc:  # noqa: BLE001 - one bad ticker must not stop the run
            logger.warning("yahoo_info_failed symbol=%s error=%s", symbol, type(exc).__name__)
            continue
        statement_roe = None if _num(info.get("returnOnEquity")) is not None else _statement_roe(ticker)
        out.append(snapshot_from_info(symbol, info, statement_roe))
        time.sleep(pause)
    return out


def run(symbols: list[str], out: Path, *, now: datetime | None = None, factory: Callable | None = None, pause: float = 0.3) -> dict[str, object]:
    moment = now or datetime.now(timezone.utc)
    snapshots = fetch_snapshots(symbols, pause=pause, factory=factory)
    groups = peer_groups(snapshots)
    ranks = percentile_ranks(snapshots)
    today = moment.astimezone(timezone.utc).date()
    fresh = [
        row
        for item in snapshots
        for row in rows_for(
            item,
            groups[item.symbol].median_pe if item.symbol in groups else None,
            moment,
            today,
            ranks.get(item.symbol),
            groups[item.symbol].count if item.symbol in groups else None,
        )
    ]
    older, newest = older_quarter_count(snapshots, today)
    if older:
        # Results season: some stocks already report the new quarter. Logged only; ranks are not changed for it.
        logger.warning("yahoo_fundamentals %d stocks on an older quarter (newest %s)", older, newest)
    merged, added = merge(read_csv(out), fresh)
    if added:
        write_csv(out, merged)
    covered = sorted({row["symbol"] for row in fresh})
    report = {"fetched": len(snapshots), "symbols_with_rows": len(covered), "rows_added": added, "missing": sorted(set(symbols) - set(covered)), "older_quarter": older}
    logger.info("yahoo_fundamentals %s", report)
    return report


def main() -> None:
    import os

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path(os.environ.get("INTELLIGENCE_FUNDAMENTALS_CSV", "/data/intelligence/fundamentals.csv")))
    parser.add_argument("--symbols", default=os.environ.get("INTELLIGENCE_SYMBOLS", ""))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    symbols = [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
    print(run(symbols, args.out))


if __name__ == "__main__":
    main()
