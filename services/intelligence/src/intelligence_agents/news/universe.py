"""NIFTY 50 tickers and name aliases used to attach RSS items to symbols."""

from __future__ import annotations

import re

NIFTY50_SYMBOLS: tuple[str, ...] = (
    "ADANIENT",
    "ADANIPORTS",
    "APOLLOHOSP",
    "ASIANPAINT",
    "AXISBANK",
    "BAJAJ-AUTO",
    "BAJAJFINSV",
    "BAJFINANCE",
    "BHARTIARTL",
    "BPCL",
    "BRITANNIA",
    "CIPLA",
    "COALINDIA",
    "DIVISLAB",
    "DRREDDY",
    "EICHERMOT",
    "GRASIM",
    "HCLTECH",
    "HDFCBANK",
    "HDFCLIFE",
    "HEROMOTOCO",
    "HINDALCO",
    "HINDUNILVR",
    "ICICIBANK",
    "INDUSINDBK",
    "INFY",
    "ITC",
    "JSWSTEEL",
    "KOTAKBANK",
    "LT",
    "LTIM",
    "M&M",
    "MARUTI",
    "NESTLEIND",
    "NTPC",
    "ONGC",
    "POWERGRID",
    "RELIANCE",
    "SBILIFE",
    "SBIN",
    "SUNPHARMA",
    "TATACONSUM",
    "TATAMOTORS",
    "TATAPOWER",
    "TATASTEEL",
    "TCS",
    "TECHM",
    "TITAN",
    "ULTRACEMCO",
    "WIPRO",
)

# Longer aliases first so "HDFC Bank" wins over a generic "HDFC" collision in caller order.
COMPANY_ALIASES: dict[str, tuple[str, ...]] = {
    "ADANIENT": ("Adani Enterprises",),
    "ADANIPORTS": ("Adani Ports",),
    "APOLLOHOSP": ("Apollo Hospitals",),
    "ASIANPAINT": ("Asian Paints",),
    "AXISBANK": ("Axis Bank",),
    "BAJAJ-AUTO": ("Bajaj Auto",),
    "BAJAJFINSV": ("Bajaj Finserv",),
    "BAJFINANCE": ("Bajaj Finance",),
    "BHARTIARTL": ("Bharti Airtel", "Airtel"),
    "BPCL": ("Bharat Petroleum",),
    "BRITANNIA": ("Britannia Industries", "Britannia"),
    "CIPLA": ("Cipla",),
    "COALINDIA": ("Coal India",),
    "DIVISLAB": ("Divi's Laboratories", "Divis Lab",),
    "DRREDDY": ("Dr Reddy", "Dr. Reddy",),
    "EICHERMOT": ("Eicher Motors", "Royal Enfield",),
    "GRASIM": ("Grasim",),
    "HCLTECH": ("HCL Tech", "HCL Technologies",),
    "HDFCBANK": ("HDFC Bank",),
    "HDFCLIFE": ("HDFC Life",),
    "HEROMOTOCO": ("Hero MotoCorp", "Hero Motocorp",),
    "HINDALCO": ("Hindalco",),
    "HINDUNILVR": ("Hindustan Unilever", "HUL"),
    "ICICIBANK": ("ICICI Bank",),
    "INDUSINDBK": ("IndusInd Bank", "Indusind Bank",),
    "INFY": ("Infosys",),
    "ITC": ("ITC Ltd", "ITC Limited"),
    "JSWSTEEL": ("JSW Steel",),
    "KOTAKBANK": ("Kotak Mahindra Bank", "Kotak Bank",),
    "LT": ("Larsen & Toubro", "Larsen and Toubro"),
    "LTIM": ("LTIMindtree", "LTI Mindtree",),
    "M&M": ("Mahindra & Mahindra", "Mahindra and Mahindra",),
    "MARUTI": ("Maruti Suzuki", "Maruti"),
    "NESTLEIND": ("Nestle India", "Nestlé India",),
    "NTPC": ("NTPC",),
    "ONGC": ("Oil and Natural Gas", "ONGC"),
    "POWERGRID": ("Power Grid", "Powergrid",),
    "RELIANCE": ("Reliance Industries", "Reliance Jio", "Jio-BlackRock"),
    "SBILIFE": ("SBI Life",),
    "SBIN": ("State Bank of India",),
    "SUNPHARMA": ("Sun Pharma", "Sun Pharmaceutical",),
    "TATACONSUM": ("Tata Consumer",),
    "TATAMOTORS": ("Tata Motors",),
    "TATAPOWER": ("Tata Power",),
    "TATASTEEL": ("Tata Steel",),
    "TCS": ("Tata Consultancy", "TCS"),
    "TECHM": ("Tech Mahindra",),
    "TITAN": ("Titan Company", "Titan"),
    "ULTRACEMCO": ("UltraTech Cement", "Ultratech"),
    "WIPRO": ("Wipro",),
}

DEFAULT_MARKET_FEEDS: tuple[str, ...] = (
    "https://news.google.com/rss/search?q=Nifty+50+OR+NSE+India&hl=en-IN&gl=IN&ceid=IN:en",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
)


def google_news_symbol_feed(symbol: str) -> str:
    query = f"{symbol} NSE OR {symbol} BSE"
    aliases = COMPANY_ALIASES.get(symbol.upper(), ())
    if aliases:
        query = f"{aliases[0]} OR {symbol} NSE"
    from urllib.parse import quote_plus

    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=en-IN&gl=IN&ceid=IN:en"
    )


def match_symbols(text: str, universe: set[str]) -> tuple[list[str], dict[str, str]]:
    """Return mapped tickers and the evidence string used for each match."""
    haystack = text or ""
    upper = haystack.upper()
    evidence: dict[str, str] = {}
    for ticker in sorted(universe, key=len, reverse=True):
        ticker_u = ticker.upper()
        pattern = r"(?<![A-Z0-9])" + re.escape(ticker_u) + r"(?![A-Z0-9])"
        if re.search(pattern, upper):
            evidence[ticker_u] = f"ticker:{ticker_u}"
            continue
        for alias in COMPANY_ALIASES.get(ticker_u, ()):
            if alias and alias.upper() in upper:
                evidence[ticker_u] = f"alias:{alias}"
                break
    return sorted(evidence), evidence
