"""Snapshot export and replay. Visibility is the candle end, not the start."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from contracts.enums import Exchange, Timeframe
from contracts.schemas.market import Candle
from core_db.repository import CoreRepository
from core_features.engine import build_feature_set
from core_market_data.replay import HistoricalReplayMarketDataProvider
from core_market_data.snapshot import _FORBIDDEN, export_snapshot, validate_snapshot
from core_market_data.zerodha import RequestPace, ZerodhaMarketDataProvider

UTC = timezone.utc
T = datetime(2024, 6, 3, 10, 0, tzinfo=UTC)


def _bar(symbol: str, end: datetime, close: str, *, start: datetime | None = None) -> Candle:
    return Candle(
        symbol=symbol,
        exchange=Exchange.NSE,
        timeframe=Timeframe.D1,
        open=Decimal(close) - Decimal("1"),
        high=Decimal(close) + Decimal("1"),
        low=Decimal(close) - Decimal("2"),
        close=Decimal(close),
        volume=100,
        start=start or (end - timedelta(hours=6)),
        end=end,
    )


def test_export_is_stable_lists_empty_symbols_and_has_no_credentials(repository: CoreRepository, tmp_path: Path) -> None:
    repository.upsert_candles([_bar("TCS", T, "2075.00"), _bar("RELIANCE", T, "1167.70")])
    first = export_snapshot(repository, tmp_path / "a", as_of=T + timedelta(days=1), created_at=datetime(2026, 10, 4, tzinfo=UTC))
    second = export_snapshot(repository, tmp_path / "b", as_of=T + timedelta(days=1), created_at=datetime(2026, 10, 5, tzinfo=UTC))
    assert first.manifest["candle_sha256"] == second.manifest["candle_sha256"]
    assert first.manifest["snapshot_id"] == "nifty50_1d_5m_20240603"
    assert first.manifest["snapshot_id"] != first.manifest["candle_sha256"]
    assert first.manifest["schema_version"] == "1.0"
    assert first.manifest["created_at"] != second.manifest["created_at"]
    candle_text = (tmp_path / "a" / "candles.jsonl").read_text(encoding="utf-8")
    text = candle_text + (tmp_path / "a" / "manifest.json").read_text(encoding="utf-8")
    for secret in _FORBIDDEN:
        assert secret not in text
    symbols = [json.loads(line)["symbol"] for line in candle_text.splitlines()]
    assert symbols == ["RELIANCE", "TCS"]
    row = json.loads((tmp_path / "a" / "candles.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert isinstance(row["open"], float)
    assert row["start"].endswith("+00:00")
    assert row["end"].endswith("+00:00")
    listed = {item["symbol"]: item for item in first.manifest["symbols"]}
    assert len(listed) == 50
    assert listed["TATAMOTORS"]["count"] == 0
    assert listed["TATAMOTORS"]["first_bar"] is None
    assert listed["TATAMOTORS"]["last_bar"] is None
    assert listed["RELIANCE"]["count"] == 1


def test_replay_hides_a_bar_that_starts_before_as_of_and_ends_after_it(repository: CoreRepository, tmp_path: Path) -> None:
    knowable = _bar("RELIANCE", T, "100")
    later = _bar("RELIANCE", T + timedelta(days=1), "200", start=T - timedelta(hours=1))
    repository.upsert_candles([knowable, later])
    export_snapshot(repository, tmp_path, as_of=T + timedelta(days=2), symbols=("RELIANCE",))
    replay = HistoricalReplayMarketDataProvider.from_snapshot(tmp_path, T + timedelta(days=2))
    visible = replay.get_candles("RELIANCE", Timeframe.D1, T - timedelta(days=10), T)
    assert [bar.end for bar in visible] == [T]
    assert replay.get_latest_candle("RELIANCE", Timeframe.D1).end == T + timedelta(days=1)
    quote = replay.get_quote("RELIANCE", T)
    assert quote.last_price == Decimal("100")
    assert quote.timestamp <= T


class _SameBars:
    def __init__(self, bars: list[dict[str, object]]) -> None:
        self._bars = bars

    def instruments(self, exchange: str) -> list[dict[str, object]]:
        return []

    def quote(self, key: str) -> dict[str, object]:
        return {}

    def historical_data(self, instrument_token: int, from_date: datetime, to_date: datetime, interval: str) -> list[dict[str, object]]:
        return self._bars

    def login_url(self) -> str:
        return "https://kite.example"

    def generate_session(self, request_token: str) -> dict[str, object]:
        return {}


def test_feature_sets_match_when_the_candle_inputs_match(repository: CoreRepository, tmp_path: Path) -> None:
    first = _bar("RELIANCE", T - timedelta(days=1), "100")
    second = _bar("RELIANCE", T, "110")
    spanning = _bar("RELIANCE", T + timedelta(days=1), "900", start=T - timedelta(hours=2))
    repository.upsert_instrument(symbol="RELIANCE", exchange="NSE", trading_symbol="RELIANCE", instrument_token=1)
    repository.upsert_candles([first, second, spanning])
    export_snapshot(repository, tmp_path, as_of=T + timedelta(days=2), symbols=("RELIANCE",))
    kite_rows = []
    for bar in (first, second, spanning):
        kite_rows.append(
            {
                "date": bar.end.astimezone(UTC).replace(tzinfo=None),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
        )
    live = ZerodhaMarketDataProvider(repository, _SameBars(kite_rows), pace=RequestPace(0))
    live_bars = live.get_candles("RELIANCE", Timeframe.D1, T - timedelta(days=10), T)
    replay = HistoricalReplayMarketDataProvider.from_snapshot(tmp_path, T + timedelta(days=2))
    replay_bars = replay.get_candles("RELIANCE", Timeframe.D1, T - timedelta(days=10), T)
    assert [(bar.end, bar.close) for bar in live_bars] == [(bar.end, bar.close) for bar in replay_bars]
    assert all(bar.end <= T for bar in live_bars)
    live_features = build_feature_set("RELIANCE", Timeframe.D1, live_bars, T)
    replay_features = build_feature_set("RELIANCE", Timeframe.D1, replay_bars, T)
    assert live_features is not None and replay_features is not None
    assert live_features.model_dump() == replay_features.model_dump()


def test_one_timeframe_export_uses_the_latest_bar_date(repository: CoreRepository, tmp_path: Path) -> None:
    repository.upsert_candles(
        [
            _bar("RELIANCE", T, "10"),
            _bar("RELIANCE", T, "11", start=T - timedelta(minutes=5)).model_copy(
                update={"timeframe": Timeframe.M5}
            ),
        ]
    )
    exported = export_snapshot(
        repository,
        tmp_path,
        as_of=T,
        symbols=("RELIANCE",),
        timeframes=(Timeframe.D1,),
    )
    assert exported.manifest["timeframes"] == ["1d"]
    assert exported.manifest["snapshot_id"] == "nifty50_1d_20240603"
    assert "5m" not in (tmp_path / "candles.jsonl").read_text(encoding="utf-8")


def test_validate_snapshot_checks_the_exported_folder(repository: CoreRepository, tmp_path: Path) -> None:
    repository.upsert_candles([_bar("RELIANCE", T, "10")])
    export_snapshot(repository, tmp_path, as_of=T + timedelta(days=1))
    window = dict(window_start=datetime(2024, 1, 1, tzinfo=UTC), window_end=T + timedelta(days=1))
    assert validate_snapshot(tmp_path, **window) == []
    path = tmp_path / "candles.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + path.read_text(encoding="utf-8"), encoding="utf-8")
    problems = validate_snapshot(tmp_path, **window)
    assert any("candle_sha256" in item or "duplicate" in item for item in problems)
