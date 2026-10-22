"""Kite Connect v4 client. Tests inject a stand-in and never construct this against the network."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

# Zerodha reads historical from/to as an IST wall clock with no offset.
IST = ZoneInfo("Asia/Kolkata")
_KITE_STAMP = "%Y-%m-%d %H:%M:%S"


def kite_historical_bound(moment: datetime) -> datetime | str:
    """Format one historical boundary for Kite.

    A timezone-aware instant is converted to Asia/Kolkata and printed without
    an offset. Repeating that conversion on the same instant, or on that
    instant already expressed in IST, yields the same string.

    A naive datetime is returned unchanged. Callers that omit a timezone
    already mean an IST wall clock, which is also how naive stamps in Kite
    responses are read. Attaching IST and converting again would move the clock.
    """
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(IST).strftime(_KITE_STAMP)


class KiteConnectMarketClient:
    """Wraps pykiteconnect. Historical calls stay non-continuous equity candles."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        access_token: str | None = None,
        kite: Any | None = None,
    ) -> None:
        self._api_secret = api_secret
        self.access_token = access_token
        if kite is None:
            from kiteconnect import KiteConnect

            kite = KiteConnect(api_key=api_key)
            if access_token:
                kite.set_access_token(access_token)
        self._kite = kite

    def login_url(self) -> str:
        return str(self._kite.login_url())

    def generate_session(self, request_token: str) -> dict[str, Any]:
        data = self._kite.generate_session(request_token, api_secret=self._api_secret)
        token = data.get("access_token")
        if token:
            self.access_token = str(token)
            self._kite.set_access_token(self.access_token)
        return dict(data)

    def use_access_token(self, token: str) -> None:
        """Reuse a token issued earlier today (restored after a restart)."""
        self.access_token = token
        self._kite.set_access_token(token)

    def instruments(self, exchange: str) -> list[dict[str, Any]]:
        return list(self._kite.instruments(exchange))

    def quote(self, key: str) -> dict[str, Any]:
        return dict(self._kite.quote(key))

    def historical_data(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str,
    ) -> list[dict[str, Any]]:
        rows = self._kite.historical_data(
            instrument_token,
            kite_historical_bound(from_date),
            kite_historical_bound(to_date),
            interval,
            continuous=False,
            oi=False,
        )
        return list(rows)


def kite_client_from_env() -> KiteConnectMarketClient | None:
    api_key = os.environ.get("ZERODHA_API_KEY", "").strip()
    api_secret = os.environ.get("ZERODHA_API_SECRET", "").strip()
    if not api_key or not api_secret:
        return None
    access_token = os.environ.get("ZERODHA_ACCESS_TOKEN", "").strip() or None
    return KiteConnectMarketClient(api_key, api_secret, access_token)
