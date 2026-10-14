"""Map NIFTY 50 company names in headlines to NSE symbols.

Headlines name companies ("Infosys", "HDFC Bank", "Larsen & Toubro") more
often than tickers. Phrases are matched case-insensitively on word
boundaries, longest first, and a matched span is consumed so "SBI Life" does
not also count as "SBI". Bare tickers still match, but only in upper case, so
"ITC" matches and "pitch" or "itc" do not. Ambiguous names are left out:
bare "HDFC", "Bajaj", "Adani", "Tata", "Reliance", and "Mahindra".
"""

from __future__ import annotations

import re

ALIASES: dict[str, tuple[str, ...]] = {
    "ADANIENT": ("Adani Enterprises",),
    "ADANIPORTS": ("Adani Ports", "Adani Ports and SEZ", "APSEZ"),
    "APOLLOHOSP": ("Apollo Hospitals",),
    "ASIANPAINT": ("Asian Paints",),
    "AXISBANK": ("Axis Bank",),
    "BAJAJ-AUTO": ("Bajaj Auto",),
    "BAJFINANCE": ("Bajaj Finance",),
    "BAJAJFINSV": ("Bajaj Finserv",),
    "BEL": ("Bharat Electronics",),
    "BHARTIARTL": ("Bharti Airtel", "Airtel"),
    "BPCL": ("Bharat Petroleum",),
    "BRITANNIA": ("Britannia",),
    "CIPLA": ("Cipla",),
    "COALINDIA": ("Coal India",),
    "DRREDDY": ("Dr Reddy's", "Dr. Reddy's", "Dr Reddys", "Dr Reddy"),
    "EICHERMOT": ("Eicher Motors", "Royal Enfield"),
    "GRASIM": ("Grasim",),
    "HCLTECH": ("HCL Technologies", "HCL Tech", "HCLTech"),
    "HDFCBANK": ("HDFC Bank",),
    "HDFCLIFE": ("HDFC Life",),
    "HEROMOTOCO": ("Hero MotoCorp", "Hero Moto"),
    "HINDALCO": ("Hindalco",),
    "HINDUNILVR": ("Hindustan Unilever", "HUL"),
    "ICICIBANK": ("ICICI Bank",),
    "INDUSINDBK": ("IndusInd Bank", "IndusInd"),
    "INFY": ("Infosys",),
    "ITC": (),
    "JSWSTEEL": ("JSW Steel",),
    "KOTAKBANK": ("Kotak Mahindra Bank", "Kotak Bank", "Kotak"),
    "LT": ("Larsen & Toubro", "Larsen and Toubro", "L&T"),
    "M&M": ("Mahindra & Mahindra", "Mahindra and Mahindra"),
    "MARUTI": ("Maruti Suzuki", "Maruti"),
    "NESTLEIND": ("Nestle India",),
    "NTPC": (),
    "ONGC": ("Oil and Natural Gas Corporation",),
    "POWERGRID": ("Power Grid",),
    "RELIANCE": ("Reliance Industries", "RIL"),
    "SBILIFE": ("SBI Life",),
    "SBIN": ("State Bank of India", "SBI"),
    "SHRIRAMFIN": ("Shriram Finance",),
    "SUNPHARMA": ("Sun Pharma", "Sun Pharmaceutical"),
    "TATACONSUM": ("Tata Consumer",),
    "TMPV": ("Tata Motors Passenger Vehicles", "Tata Motors PV"),
    "TATASTEEL": ("Tata Steel",),
    "TCS": ("Tata Consultancy Services", "Tata Consultancy"),
    "TECHM": ("Tech Mahindra",),
    "TITAN": ("Titan Company", "Titan"),
    "TRENT": ("Trent",),
    "ULTRACEMCO": ("UltraTech Cement", "UltraTech"),
    "WIPRO": ("Wipro",),
}

_TICKER = re.compile(r"(?<![A-Za-z0-9&-])([A-Z][A-Z0-9&-]{1,11})(?![A-Za-z0-9&-])")


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    escaped = re.escape(phrase).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)


def build_matcher(universe: set[str]) -> list[tuple[re.Pattern[str], str]]:
    phrases = [(phrase, symbol) for symbol, names in ALIASES.items() if symbol in universe for phrase in names]
    phrases.sort(key=lambda item: len(item[0]), reverse=True)
    return [(_phrase_pattern(phrase), symbol) for phrase, symbol in phrases]


def map_symbols(text: str, universe: set[str], matcher: list[tuple[re.Pattern[str], str]] | None = None) -> list[str]:
    """Return the sorted NIFTY symbols a headline or summary mentions."""
    found: set[str] = set()
    remaining = text
    for pattern, symbol in matcher if matcher is not None else build_matcher(universe):
        if pattern.search(remaining):
            found.add(symbol)
            remaining = pattern.sub(" ", remaining)
    for match in _TICKER.finditer(remaining):
        token = match.group(1)
        if token in universe:
            found.add(token)
    return sorted(found)
