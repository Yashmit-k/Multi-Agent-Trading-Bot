"""Pre-registered event study: news-category volume spikes versus the NIFTY 50 index.

The rules live in services/quant/docs/news-categories-nifty-protocol.md.
This module does not score agents, place orders, or change fusion.
"""

from __future__ import annotations

import hashlib
import json
import math
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

import numpy as np


IST = timezone(timedelta(hours=5, minutes=30))
SESSION_CLOSE = time(15, 30)
SESSION_OPEN = time(9, 15)
GDELT_DOC = "https://api.gdeltproject.org/api/v2/doc/doc"
VOLUME_START = date(2017, 1, 1)
TRAIN_START = date(2017, 1, 1)
TRAIN_END = date(2022, 12, 31)
VALIDATE_START = date(2023, 1, 1)
RV_START = date(2024, 1, 1)
WINDOW = 60
Z_SCORE = 2.0
BLOCK = 5
N_BOOT = 5000
BOOT_SEED = 0
MISMATCH_TOLERANCE = 0.005

OUTCOMES: tuple[str, ...] = (
    "ret_0",
    "ret_1",
    "ret_1_5",
    "abs_0",
    "abs_1",
    "abs_1_5",
    "vix_0",
    "vix_1",
    "vix_1_5",
    "rv_0",
    "rv_1",
    "rv_1_5",
)

# Queries are the protocol text, character for character.
CATEGORIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "geopolitics_war",
        "Geopolitics and war",
        (
            '(war OR warfare OR invasion OR bombardment OR "missile strike" OR "missile strikes" OR "military escalation" OR "terror attack" OR "terrorist attack")',
            '("India Pakistan" OR "India-Pakistan" OR "Line of Control") AND (strike OR attack OR shelling OR ceasefire OR tension OR conflict)',
            '("India China" OR "India-China" OR Galwan OR Ladakh OR "Line of Actual Control") AND (clash OR standoff OR incursion OR tension OR border)',
        ),
    ),
    (
        "crude_commodities",
        "Crude oil and commodity shocks",
        (
            '(crude OR brent OR OPEC OR "oil price" OR "oil prices") AND (surge OR jump OR plunge OR shock OR spike OR slump OR embargo OR "supply cut")',
            '("commodity prices" OR "commodities selloff" OR "gold price") AND (surge OR jump OR plunge OR shock OR record)',
        ),
    ),
    (
        "central_banks",
        "Central banks",
        (
            '("Reserve Bank of India" OR "repo rate" OR "monetary policy committee" OR "RBI policy")',
            '("Federal Reserve" OR FOMC OR "Fed rate" OR "interest rate decision") AND (hike OR cut OR hold OR pause OR decision)',
        ),
    ),
    (
        "inflation_macro",
        "Inflation and macro data",
        (
            '(CPI OR "consumer price index" OR "retail inflation" OR "wholesale inflation") AND (India OR Indian)',
            '(GDP OR "gross domestic product" OR IIP OR "industrial production") AND (India OR Indian)',
        ),
    ),
    (
        "india_policy",
        "Indian government policy, budget, and tax",
        (
            '("Union Budget" OR "India budget" OR "finance bill") AND (India OR Indian)',
            '(GST OR "tax cut" OR "tax hike" OR "import duty" OR "government policy") AND (India OR Indian OR "New Delhi")',
        ),
    ),
    (
        "elections",
        "Elections and political instability",
        (
            '("Lok Sabha" OR "assembly election" OR "general election" OR "vote counting") AND (India OR Indian)',
            '("political crisis" OR "no-confidence" OR "coalition" OR resignation) AND (India OR "prime minister" OR "chief minister")',
        ),
    ),
    (
        "global_selloff",
        "Global market sell-offs",
        (
            '("S&P 500" OR Nasdaq OR "Dow Jones" OR "Wall Street") AND (plunge OR selloff OR "sell-off" OR crash OR tumble OR slump)',
            '(Shanghai OR "Hong Kong stocks" OR "China stocks" OR "CSI 300") AND (plunge OR selloff OR crash OR tumble OR slump)',
        ),
    ),
    (
        "fii_rupee",
        "Foreign investor flows and the rupee",
        (
            '(FII OR FPI OR "foreign institutional" OR "foreign portfolio") AND (outflow OR inflow OR selling OR buying OR selloff)',
            '(rupee) AND (slide OR slump OR "record low" OR "all-time low" OR depreciation OR weakens OR tumbles)',
        ),
    ),
    (
        "disasters_pandemics",
        "Disasters and pandemics",
        (
            "(pandemic OR COVID OR COVID-19 OR coronavirus OR lockdown)",
            "(earthquake OR cyclone OR flood OR landslide) AND (India OR Indian)",
        ),
    ),
    (
        "trade_wars",
        "Trade wars, tariffs, and sanctions",
        (
            '("trade war" OR tariff OR tariffs OR sanctions OR "trade dispute") AND (China OR India OR "United States" OR US OR Trump OR Biden)',
        ),
    ),
)



def event_flags(volume: Sequence[float], *, window: int = WINDOW, z: float = Z_SCORE) -> list[bool]:
    """True when today's volume is at least z sample-SDs above the previous `window` days.

    Index i uses volume[i - window : i] only. The value at i, and everything after it,
    cannot change a flag at or before i.
    """
    if window < 2:
        raise ValueError("window must be at least 2")
    values = [float(item) for item in volume]
    flags = [False] * len(values)
    for index in range(window, len(values)):
        past = values[index - window : index]
        mean = sum(past) / window
        var = sum((item - mean) ** 2 for item in past) / (window - 1)
        if var <= 0.0:
            continue
        if values[index] >= mean + z * math.sqrt(var):
            flags[index] = True
    return flags




def _as_ist(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return moment.astimezone(IST)


def assign_timestamp(moment: datetime, sessions: Sequence[date]) -> date | None:
    """Session that may trade on a timestamped headline.

    Before 15:30 IST on a session, that session. At 15:30 or later, or on a
    day that is not a session, the next session after the IST date.
    """
    ist = _as_ist(moment)
    day = ist.date()
    ordered = tuple(sorted(sessions))
    if day in set(ordered) and ist.time() < SESSION_CLOSE:
        return day
    for session in ordered:
        if session > day:
            return session
    return None


def assign_gdelt_day(day: date, sessions: Sequence[date]) -> date | None:
    """GDELT daily buckets have no clock, so they always take the next session."""
    for session in sorted(sessions):
        if session > day:
            return session
    return None


def event_sessions(days: Sequence[tuple[date, bool]], sessions: Sequence[date]) -> set[date]:
    """Map event calendar days onto sessions. Two days can share one session."""
    found: set[date] = set()
    for day, flag in days:
        if not flag:
            continue
        session = assign_gdelt_day(day, sessions)
        if session is not None:
            found.add(session)
    return found


