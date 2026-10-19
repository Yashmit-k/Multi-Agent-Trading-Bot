"""Yahoo fundamentals fetch: field mapping, staleness, peer medians, append-only merge, and agent scoring."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from intelligence_agents.agents.fundamental import fundamental_score
from intelligence_agents.fundamentals.csv_loader import load_csv_text
from intelligence_agents.fundamentals.yahoo import merge, peer_medians, quarter_label, read_csv, rows_for, run, snapshot_from_info

NOW = datetime(2026, 10, 19, 15, 30, tzinfo=timezone.utc)
QUARTER = datetime(2026, 9, 30, tzinfo=timezone.utc).timestamp()


def _info(**extra):  # type: ignore[no-untyped-def]
    base = {"mostRecentQuarter": QUARTER, "trailingEps": 50.0, "trailingPE": 20.0, "earningsQuarterlyGrowth": 0.12, "revenueGrowth": 0.08,
            "profitMargins": 0.15, "returnOnEquity": 0.2, "debtToEquity": 35.0, "sector": "Technology"}
    return {**base, **extra}


def test_mapping_converts_debt_percent_and_labels_the_quarter() -> None:
    snap = snapshot_from_info("TCS", _info())
    assert snap.debt_to_equity == 0.35 and snap.quarter_end == date(2026, 9, 30)
    assert quarter_label(date(2026, 9, 30)) == "2026Q3"
    rows = rows_for(snap, 22.0, NOW, NOW.date())
    by_metric = {row["metric"]: row for row in rows}
    assert by_metric["eps"]["source_id"] == "TCS-2026Q3-eps" and by_metric["eps"]["available_at"] == NOW.isoformat()
    assert by_metric["peer_median_pe"]["value"] == "22.0"


def test_stale_or_undated_quarters_write_nothing() -> None:
    old = datetime(2025, 6, 30, tzinfo=timezone.utc).timestamp()
    assert rows_for(snapshot_from_info("HDFCBANK", _info(mostRecentQuarter=old)), None, NOW, NOW.date()) == []
    assert rows_for(snapshot_from_info("HDFCBANK", _info(mostRecentQuarter=None)), None, NOW, NOW.date()) == []


def test_peer_median_uses_sector_with_three_peers_else_all() -> None:
    snaps = [snapshot_from_info(name, _info(trailingPE=pe, sector=sector)) for name, pe, sector in
             [("A", 10, "Tech"), ("B", 20, "Tech"), ("C", 30, "Tech"), ("D", 50, "Retail"), ("E", -5, "Tech")]]
    medians = peer_medians(snaps)
    assert medians["A"] == 20 and medians["D"] == 25  # Retail has one peer: falls back to all-stock median
    assert "E" not in medians  # negative P/E is not a peer


def test_merge_never_rewrites_and_keeps_revisions() -> None:
    first = rows_for(snapshot_from_info("TCS", _info()), 22.0, NOW, NOW.date())
    merged, added = merge([], first)
    assert added == len(first)
    again, added = merge(merged, first)
    assert added == 0
    later = NOW + timedelta(days=1)
    revised = rows_for(snapshot_from_info("TCS", _info(trailingEps=51.0)), 22.0, later, later.date())
    after, added = merge(again, revised)
    eps_rows = [row for row in after if row["metric"] == "eps"]
    assert [row["value"] for row in eps_rows] == ["50.0", "51.0"] and eps_rows[1]["source_id"].startswith("TCS-2026Q3-eps~rev")


def test_run_writes_a_csv_the_loader_accepts(tmp_path: Path) -> None:
    class Ticker:
        def __init__(self, name: str) -> None:
            self.info = _info() if name != "BAD.NS" else None

    out = tmp_path / "fundamentals.csv"
    report = run(["TCS", "INFY", "BAD"], out, now=NOW, factory=Ticker, pause=0)
    assert report["symbols_with_rows"] == 2 and report["missing"] == ["BAD"]

    class Store:
        def __init__(self) -> None:
            self.points = []

        def insert(self, point):  # type: ignore[no-untyped-def]
            self.points.append(point)
            return True

    store = Store()
    assert load_csv_text(store, out.read_text()) == len(read_csv(out))
    assert {point.metric for point in store.points} >= {"eps", "peer_median_pe", "profit_growth", "roe"}


def test_fundamental_score_parts_and_bounds() -> None:
    score, parts = fundamental_score({"profit_growth": Decimal("0.25"), "revenue_growth": Decimal("0.15"), "roe": Decimal("0.24"), "debt_to_equity": Decimal("0")})
    assert score == 1.0 and set(parts) == {"profit_growth", "revenue_growth", "roe", "debt_to_equity"}
    weak, _ = fundamental_score({"profit_growth": Decimal("-0.5"), "roe": Decimal("0.0")})
    assert weak == -1.0
    assert fundamental_score({"eps": Decimal("10")}) == (0.0, {})
