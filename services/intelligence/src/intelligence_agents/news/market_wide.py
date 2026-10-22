"""Keyword categories for headlines that name no NIFTY 50 company.

The ten ids match the pre-registered study. A headline that matches none is
"unclassified". This does not score a stock and it does not vote in fusion.
"""

from __future__ import annotations

import re

# First matching category wins. Phrases are matched on word boundaries.
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "trade_wars",
        ("trade war", "trade dispute", "tariff", "tariffs", "sanction", "sanctions"),
    ),
    (
        "geopolitics_war",
        (
            "missile",
            "invasion",
            "terror",
            "terrorist",
            "shelling",
            "ceasefire",
            "galwan",
            "ladakh",
            "strike",
            "strikes",
            "war",
        ),
    ),
    (
        "crude_commodities",
        ("brent", "crude", "opec", "oil price", "oil prices", "commodity", "commodities"),
    ),
    (
        "central_banks",
        ("reserve bank of india", "repo rate", "monetary policy committee", "rbi", "federal reserve", "fomc", "fed rate"),
    ),
    (
        "inflation_macro",
        ("consumer price", "retail inflation", "wholesale inflation", "cpi", "gdp", "iip", "industrial production", "inflation"),
    ),
    (
        "india_policy",
        ("union budget", "finance bill", "import duty", "gst", "tax cut", "tax hike"),
    ),
    (
        "elections",
        ("lok sabha", "assembly election", "general election", "vote counting", "no-confidence", "election"),
    ),
    (
        "global_selloff",
        ("s&p", "nasdaq", "dow jones", "wall street", "shanghai", "csi 300", "sell-off", "selloff"),
    ),
    (
        "fii_rupee",
        ("foreign institutional", "foreign portfolio", "fii", "fpi", "rupee"),
    ),
    (
        "disasters_pandemics",
        ("pandemic", "covid", "coronavirus", "lockdown", "earthquake", "cyclone", "flood", "landslide"),
    ),
)


def categorise(text: str) -> str:
    """Return one of the ten category ids, or unclassified."""
    haystack = text.lower()
    for category, phrases in _RULES:
        for phrase in phrases:
            if re.search(rf"\b{re.escape(phrase)}\b", haystack):
                return category
    return "unclassified"
