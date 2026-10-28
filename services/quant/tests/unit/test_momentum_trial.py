"""Momentum paper trial: sessions skip NSE holidays; decisions are logged once and a changed ranking is flagged."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from quant_agents import momentum_trial as mt


def test_next_session_skips_weekends_and_holidays() -> None:
    assert mt.next_session(date(2026, 9, 30)) == date(2026, 10, 1)
    assert mt.next_session(date(2026, 10, 1)) == date(2026, 10, 5)  # 2 Oct holiday, then the weekend


class _M:
    def __init__(self, days: list[date]) -> None:
        self.d = days
        self.members = {k: [] for k in range(len(days))}


def test_decisions_are_recorded_once_and_changes_flagged(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mt, "DIR", tmp_path)
    monkeypatch.setattr(mt, "START", date(2026, 10, 30))
    m = _M([date(2026, 9, 30), date(2026, 10, 30)])
    ranked = [{"rank": 1, "symbol": "AAA", "score": 1.0, "close": 10.0}]
    monkeypatch.setattr(mt, "ranking", lambda m, wm, t, scorer=None: ranked)
    now = datetime(2026, 10, 30, 15, tzinfo=timezone.utc)
    assert mt.record_decisions(m, None, now) == ["plain: decision recorded for 2026-10-30"]
    assert mt.record_decisions(m, None, now) == []
    rows = [json.loads(line) for line in (tmp_path / "decisions.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["trade_at_open_of"] == "2026-11-02"
    monkeypatch.setattr(mt, "ranking", lambda m, wm, t, scorer=None: [{"rank": 1, "symbol": "BBB", "score": 2.0, "close": 5.0}])
    assert mt.record_decisions(m, None, now)[0].startswith("WARNING")
    assert len((tmp_path / "decisions.jsonl").read_text().splitlines()) == 1


def test_next_decision_is_the_month_end_session() -> None:
    assert mt.next_decision(date(2026, 10, 28)) == date(2026, 10, 30)
    assert mt.next_decision(date(2026, 10, 30)) == date(2026, 11, 30)
    assert mt.month_end_session(date(2026, 3, 5)) == date(2026, 3, 30)  # 31 Mar 2026 is an NSE holiday


def test_delivery_book_waits_for_that_days_delivery_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mt, "DIR", tmp_path)
    monkeypatch.setattr(mt, "START", date(2026, 10, 30))
    monkeypatch.setattr(mt, "ranking", lambda m, wm, t, scorer=None: [{"rank": 1, "symbol": "AAA", "score": 1.0, "close": 10.0}])
    m = _M([date(2026, 10, 30)])
    now = datetime(2026, 10, 30, 15, tzinfo=timezone.utc)
    assert mt.record_decisions(m, None, now, "delivery") == ["delivery: waiting for the delivery file of 2026-10-30"]
    assert not (tmp_path / "decisions-delivery.jsonl").read_text()
    (tmp_path / "delivery").mkdir()
    (tmp_path / "delivery" / "2026-10-30.csv").write_text("SYMBOL\n")
    assert mt.record_decisions(m, None, now, "delivery") == ["delivery: decision recorded for 2026-10-30"]
    assert json.loads((tmp_path / "decisions-delivery.jsonl").read_text())["book"] == "delivery"
