"""Isolated collector probe. Scripted bars only. This module does not call Zerodha.

The standalone Compose file runs this process instead of the API. It keeps
polling until the process is stopped. Stopping it stops further writes.
"""

from __future__ import annotations

import os
import signal
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from contracts.enums import Exchange, Timeframe
from contracts.schemas.market import Candle
from core_db.repository import CoreRepository
from core_db.session import create_schema
from core_market_data.collector import IngestionState, run_incremental_once
from core_market_data.nse_sessions import IST
from core_market_data.zerodha import RequestPace

UTC = timezone.utc
_STOP = threading.Event()


class _ScriptedBook:
    """One five-minute bar ending on the requested window. No network client."""

    def historical_data(self, instrument_token: int, from_date: datetime, to_date: datetime, interval: str):
        if interval != "5minute":
            return []
        moment = to_date if to_date.tzinfo else to_date.replace(tzinfo=UTC)
        local = moment.astimezone(IST).replace(second=0, microsecond=0)
        floored = local.replace(minute=(local.minute // 5) * 5)
        start = (floored - timedelta(minutes=5)).astimezone(UTC)
        return [{"date": start, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1}]

    def instruments(self, exchange: str) -> list[dict[str, object]]:
        return []

    def quote(self, key: str) -> dict[str, object]:
        return {}


def main() -> None:
    url = os.environ["DATABASE_URL"]
    if urlparse_database(url) in {"", "core", "postgres"}:
        raise SystemExit("refusing a production database name")
    repository = CoreRepository(create_schema(url))
    _seed(repository)
    port = int(os.environ.get("PROBE_PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: _STOP.set())
    signal.signal(signal.SIGINT, lambda _signum, _frame: _STOP.set())
    moment = datetime(2026, 10, 13, 4, 2, tzinfo=UTC)
    client = _ScriptedBook()
    while not _STOP.is_set():
        run_incremental_once(repository, client, IngestionState(), now=moment, pace=RequestPace(0))
        moment += timedelta(minutes=5)
        _STOP.wait(0.3)
    server.shutdown()


def urlparse_database(url: str) -> str:
    path = url.split("/", 3)[-1]
    return path.split("?")[0]


def _seed(repository: CoreRepository) -> None:
    instrument = repository.upsert_instrument(symbol="RELIANCE", exchange="NSE", trading_symbol="RELIANCE", instrument_token=1)
    repository.add_membership(instrument.instrument_id, "NIFTY50", datetime(2024, 1, 1, tzinfo=UTC), None)
    repository.upsert_candles(
        [
            Candle(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe=Timeframe.D1,
                open=Decimal("10"),
                high=Decimal("11"),
                low=Decimal("9"),
                close=Decimal("10"),
                volume=1,
                start=datetime(2026, 10, 12, 3, 45, tzinfo=UTC),
                end=datetime(2026, 10, 12, 10, 0, tzinfo=UTC),
            ),
            Candle(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe=Timeframe.M5,
                open=Decimal("10"),
                high=Decimal("11"),
                low=Decimal("9"),
                close=Decimal("10"),
                volume=1,
                start=datetime(2026, 10, 13, 3, 45, tzinfo=UTC),
                end=datetime(2026, 10, 13, 3, 50, tzinfo=UTC),
            ),
        ]
    )


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b'{"status":"ok","source":"scripted"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    main()
