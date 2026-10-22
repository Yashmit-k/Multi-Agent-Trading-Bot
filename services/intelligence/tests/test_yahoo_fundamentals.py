"""Yahoo fundamentals fetch: field mapping, staleness, peer medians, append-only merge, and agent scoring."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from intelligence_agents.agents.fundamental import fundamental_score
from intelligence_agents.fundamentals.csv_loader import load_csv_text
from intelligence_agents.fundamentals.yahoo import merge, older_quarter_count, peer_groups, peer_medians, quarter_label, read_csv, rows_for, run, snapshot_from_info

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


def test_peer_median_never_includes_the_stock_itself() -> None:
    snaps = [snapshot_from_info(name, _info(trailingPE=pe, sector="Tech", industry="Software")) for name, pe in
             [("A", 10), ("B", 20), ("C", 30), ("D", 40), ("E", -5)]]
    groups = peer_groups(snaps)
    assert groups["A"].median_pe == 30 and groups["A"].count == 3  # B, C, D: A's own 10 is left out
    assert groups["D"].median_pe == 20  # A, B, C
    assert "E" not in groups  # a negative P/E has no meaningful comparison and is nobody's peer
    assert peer_medians(snaps) == {symbol: group.median_pe for symbol, group in groups.items()}


def test_peer_group_prefers_industry_then_sector_then_all() -> None:
    rows = [
        # Oil & Gas Refining: only two members, so RELIANCE falls back to its broad sector
        ("RELIANCE", 22, "Energy", "Oil & Gas Refining & Marketing"),
        ("BPCL", 8, "Energy", "Oil & Gas Refining & Marketing"),
        ("ONGC", 7, "Energy", "Oil & Gas E&P"),
        ("COALINDIA", 9, "Energy", "Thermal Coal"),
        ("NTPC", 15, "Utilities", "Utilities - Regulated Electric"),
        # Software: four members, so each one compares with the three others in its industry
        ("TCS", 28, "Technology", "Information Technology Services"),
        ("INFY", 24, "Technology", "Information Technology Services"),
        ("WIPRO", 20, "Technology", "Information Technology Services"),
        ("HCLTECH", 26, "Technology", "Information Technology Services"),
        ("TITAN", 90, "Consumer Cyclical", "Luxury Goods"),
    ]
    snaps = [snapshot_from_info(name, _info(trailingPE=pe, sector=sector, industry=industry)) for name, pe, sector, industry in rows]
    groups = peer_groups(snaps)
    assert (groups["TCS"].basis, groups["TCS"].count, groups["TCS"].median_pe) == ("industry", 3, 24)  # INFY, WIPRO, HCLTECH
    assert (groups["RELIANCE"].basis, groups["RELIANCE"].count, groups["RELIANCE"].median_pe) == ("sector", 3, 8)  # BPCL, ONGC, COALINDIA
    assert groups["TITAN"].basis == "all" and groups["TITAN"].count == 9  # alone in its sector: every other stock
    assert all(group.count <= len(snaps) - 1 for group in groups.values())  # a stock is never one of its own peers


def test_peer_count_row_sits_next_to_the_median() -> None:
    rows = rows_for(snapshot_from_info("TCS", _info()), 24.0, NOW, NOW.date(), peer_count=3)
    by_metric = {row["metric"]: row for row in rows}
    assert by_metric["peer_count"]["value"] == "3" and by_metric["peer_count"]["unit"] == "count"
    assert by_metric["peer_count"]["period"] == by_metric["peer_median_pe"]["period"]


def test_older_quarter_count_reports_results_season() -> None:
    newer = datetime(2026, 9, 30, tzinfo=timezone.utc).timestamp()
    older = datetime(2026, 6, 30, tzinfo=timezone.utc).timestamp()
    snaps = [snapshot_from_info(f"S{i}", _info(mostRecentQuarter=newer if i < 3 else older)) for i in range(5)]
    assert older_quarter_count(snaps, NOW.date()) == (2, "2026Q3")


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


def test_generated_csv_passes_the_validator_script(tmp_path: Path) -> None:
    import importlib.util

    script = Path(__file__).resolve().parents[3] / "scripts" / "validate_fundamentals_csv.py"
    spec = importlib.util.spec_from_file_location("validate_fundamentals_csv", script)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    class Ticker:
        def __init__(self, name: str) -> None:
            symbol = name.removesuffix(".NS")
            pe = {"TCS": 28.0, "INFY": 24.0, "WIPRO": 20.0, "HCLTECH": 26.0, "ITC": 16.5}[symbol]
            self.info = _info(trailingPE=pe, industry="Tobacco" if symbol == "ITC" else "Information Technology Services")

    out = tmp_path / "fundamentals.csv"
    run(["TCS", "INFY", "WIPRO", "HCLTECH", "ITC"], out, now=NOW, factory=Ticker, pause=0)
    rows = read_csv(out)
    assert module.validate(out) == []
    assert {row["value"] for row in rows if row["symbol"] == "TCS" and row["metric"] == "peer_count"} == {"3"}


def test_fundamental_score_parts_and_bounds() -> None:
    score, parts = fundamental_score({"profit_growth": Decimal("0.25"), "revenue_growth": Decimal("0.15"), "roe": Decimal("0.24"), "debt_to_equity": Decimal("0")})
    assert score == 1.0 and set(parts) == {"profit_growth", "revenue_growth", "roe", "debt_to_equity"}
    weak, _ = fundamental_score({"profit_growth": Decimal("-0.5"), "roe": Decimal("0.0")})
    assert weak == -1.0
    assert fundamental_score({"eps": Decimal("10")}) == (0.0, {})


def test_percentile_ranks_are_relative_and_lower_debt_ranks_higher() -> None:
    from intelligence_agents.fundamentals.yahoo import percentile_ranks

    snaps = [snapshot_from_info(f"S{i}", _info(earningsQuarterlyGrowth=0.05 * i, debtToEquity=10.0 * i)) for i in range(6)]
    ranks = percentile_ranks(snaps)
    assert ranks["S5"]["rank_profit_growth"] == 1.0 and ranks["S0"]["rank_profit_growth"] == 0.0
    assert ranks["S0"]["rank_debt_to_equity"] == 1.0  # least debt is best
    score, parts = fundamental_score({f"rank_{k}": Decimal(str(v[0])) for k, v in {"profit_growth": [1.0], "roe": [0.0]}.items()})
    assert parts == {"profit_growth": 1.0, "roe": -1.0} and score == 0.0
    rows = rows_for(snaps[3], 20.0, NOW, NOW.date(), ranks["S3"])
    assert {row["metric"] for row in rows} >= {"rank_profit_growth", "rank_debt_to_equity"}
