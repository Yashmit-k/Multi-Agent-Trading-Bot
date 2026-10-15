"""Portfolio-level limits for new BUYs: positions, sector, exposure, per stock, and entries per day.

The context is the active paper book at decision time: open positions at cost,
plus BUY orders that are queued but not filled yet (their cash is reserved).
"""

from dataclasses import dataclass, field
from decimal import Decimal

MAX_OPEN_POSITIONS = 10
MAX_PER_SECTOR = 2
MAX_EXPOSURE_FRACTION = Decimal("0.30")
MAX_PER_STOCK = Decimal("40000")
DAILY_ENTRY_LIMIT = 6

# NIFTY sector index per constituent. A stock without a matching index counts as its own sector.
SECTOR_OF: dict[str, str] = {
    **{s: "NIFTY BANK" for s in ("AXISBANK", "HDFCBANK", "ICICIBANK", "INDUSINDBK", "KOTAKBANK", "SBIN")},
    **{s: "NIFTY FIN SERVICE" for s in ("BAJFINANCE", "BAJAJFINSV", "HDFCLIFE", "SBILIFE", "SHRIRAMFIN")},
    **{s: "NIFTY IT" for s in ("HCLTECH", "INFY", "TCS", "TECHM", "WIPRO")},
    **{s: "NIFTY AUTO" for s in ("BAJAJ-AUTO", "EICHERMOT", "HEROMOTOCO", "M&M", "MARUTI", "TMPV")},
    **{s: "NIFTY FMCG" for s in ("BRITANNIA", "HINDUNILVR", "ITC", "NESTLEIND", "TATACONSUM")},
    **{s: "NIFTY METAL" for s in ("HINDALCO", "JSWSTEEL", "TATASTEEL")},
    **{s: "NIFTY PHARMA" for s in ("CIPLA", "DRREDDY", "SUNPHARMA")},
    **{s: "NIFTY ENERGY" for s in ("BPCL", "NTPC", "ONGC", "POWERGRID", "RELIANCE")},
    "TITAN": "NIFTY CONSR DURBL",
}


def sector_of(symbol: str) -> str:
    return SECTOR_OF.get(symbol, f"OWN:{symbol}")


@dataclass(frozen=True)
class PortfolioContext:
    starting_cash: Decimal
    exposure: dict[str, Decimal] = field(default_factory=dict)  # symbol -> cost of held shares plus queued BUYs
    entries_today: int = 0
    max_positions: int = MAX_OPEN_POSITIONS
    max_per_sector: int = MAX_PER_SECTOR
    max_exposure_fraction: Decimal = MAX_EXPOSURE_FRACTION
    max_per_stock: Decimal = MAX_PER_STOCK
    daily_entry_limit: int = DAILY_ENTRY_LIMIT

    def checks(self, symbol: str, notional: Decimal) -> list[tuple[str, bool, str]]:
        held = {name for name, value in self.exposure.items() if value > 0}
        others = held - {symbol}
        sector = sector_of(symbol)
        same_sector = sum(1 for name in others if sector_of(name) == sector)
        total = sum(self.exposure.values(), Decimal("0")) + notional
        cap = self.starting_cash * self.max_exposure_fraction
        in_stock = self.exposure.get(symbol, Decimal("0")) + notional
        return [
            ("max_open_positions", len(others) + 1 <= self.max_positions,
             f"would hold {len(others) + 1} names; limit is {self.max_positions}"),
            ("sector_concentration", same_sector + 1 <= self.max_per_sector,
             f"{sector} already has {same_sector} position(s); limit is {self.max_per_sector}"),
            ("exposure_cap", total <= cap,
             f"total exposure {total:.2f} would exceed {self.max_exposure_fraction:.0%} of starting cash ({cap:.2f})"),
            ("per_stock_cap", in_stock <= self.max_per_stock,
             f"{symbol} exposure {in_stock:.2f} would exceed {self.max_per_stock}"),
            ("daily_entry_cap", self.entries_today < self.daily_entry_limit,
             f"{self.entries_today} entries already today; limit is {self.daily_entry_limit}"),
        ]
