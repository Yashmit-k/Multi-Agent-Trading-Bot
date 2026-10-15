"""Check a fundamentals CSV before the intelligence service loads it.

Usage: python scripts/validate_fundamentals_csv.py data/intelligence/fundamentals.csv
Exit code 0 if valid; prints coverage per agent. Reads the file only.
"""

import csv
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

NIFTY50 = set(
    "ADANIENT ADANIPORTS APOLLOHOSP ASIANPAINT AXISBANK BAJAJ-AUTO BAJFINANCE BAJAJFINSV BEL BHARTIARTL BPCL BRITANNIA CIPLA "
    "COALINDIA DRREDDY EICHERMOT GRASIM HCLTECH HDFCBANK HDFCLIFE HEROMOTOCO HINDALCO HINDUNILVR ICICIBANK INDUSINDBK INFY ITC "
    "JSWSTEEL KOTAKBANK LT M&M MARUTI NESTLEIND NTPC ONGC POWERGRID RELIANCE SBILIFE SBIN SHRIRAMFIN SUNPHARMA TATACONSUM TMPV "
    "TATASTEEL TCS TECHM TITAN TRENT ULTRACEMCO WIPRO".split()
)
METRICS = {"eps", "revenue_growth", "profit_growth", "margin", "roe", "roce", "debt", "cash_flow"}
COLUMNS = ["symbol", "metric", "value", "unit", "period", "announced_at", "available_at", "source", "source_id"]


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    eps_periods: dict[str, set[str]] = defaultdict(set)
    any_metric: set[str] = set()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != COLUMNS:
            return [f"header must be exactly: {','.join(COLUMNS)}"]
        for line, row in enumerate(reader, start=2):
            where = f"line {line}"
            symbol, metric = row["symbol"].strip().upper(), row["metric"].strip()
            if symbol not in NIFTY50:
                errors.append(f"{where}: unknown symbol {symbol!r}")
            if metric not in METRICS:
                errors.append(f"{where}: metric {metric!r} not in {sorted(METRICS)}")
            try:
                Decimal(row["value"])
            except InvalidOperation:
                errors.append(f"{where}: value {row['value']!r} is not a number")
            try:
                announced = datetime.fromisoformat(row["announced_at"])
                available = datetime.fromisoformat(row["available_at"])
                if announced.tzinfo is None or available.tzinfo is None:
                    errors.append(f"{where}: timestamps need a timezone, e.g. +05:30")
                elif available < announced:
                    errors.append(f"{where}: available_at is before announced_at (look-ahead)")
            except ValueError:
                errors.append(f"{where}: timestamps must be ISO-8601")
            if row["source_id"] in seen:
                errors.append(f"{where}: duplicate source_id {row['source_id']!r}")
            seen.add(row["source_id"])
            any_metric.add(symbol)
            if metric == "eps":
                eps_periods[symbol].add(row["period"].strip())
    print(f"rows: {len(seen)}")
    print(f"Fundamental agent coverage: {len(any_metric)}/50 symbols")
    print(f"Valuation agent coverage (has eps): {len(eps_periods)}/50 symbols")
    print(f"Earnings agent coverage (eps for 2+ periods): {sum(1 for p in eps_periods.values() if len(p) >= 2)}/50 symbols")
    return errors


if __name__ == "__main__":
    problems = validate(Path(sys.argv[1]))
    for problem in problems[:50]:
        print("ERROR", problem)
    sys.exit(1 if problems else 0)
