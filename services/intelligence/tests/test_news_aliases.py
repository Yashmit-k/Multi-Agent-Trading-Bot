from intelligence_agents.news.aliases import map_symbols

UNIVERSE = {"INFY", "HDFCBANK", "HDFCLIFE", "SBIN", "SBILIFE", "LT", "ITC", "M&M", "TCS", "RELIANCE", "BAJFINANCE", "BAJAJFINSV"}


def test_company_names_map_to_symbols() -> None:
    assert map_symbols("Infosys shares jump after Q2 beat", UNIVERSE) == ["INFY"]
    assert map_symbols("HDFC Bank and Larsen & Toubro lead gains", UNIVERSE) == ["HDFCBANK", "LT"]
    assert map_symbols("Mahindra & Mahindra SUV sales rise", UNIVERSE) == ["M&M"]


def test_longest_phrase_wins() -> None:
    assert map_symbols("SBI Life premium growth slows", UNIVERSE) == ["SBILIFE"]
    assert map_symbols("SBI raises lending rates; SBI Life flat", UNIVERSE) == ["SBILIFE", "SBIN"]
    assert map_symbols("Bajaj Finserv and Bajaj Finance diverge", UNIVERSE) == ["BAJAJFINSV", "BAJFINANCE"]


def test_tickers_match_only_in_upper_case() -> None:
    assert map_symbols("ITC hotels demerger update", UNIVERSE) == ["ITC"]
    assert map_symbols("a strong pitch to investors", UNIVERSE) == []
    assert map_symbols("RELIANCE posts steady update", UNIVERSE) == ["RELIANCE"]


def test_ambiguous_names_are_ignored() -> None:
    assert map_symbols("HDFC group stocks mixed", UNIVERSE) == []
    assert map_symbols("Reliance Power hits upper circuit", UNIVERSE) == []
    assert map_symbols("Reliance Industries to raise capex", UNIVERSE) == ["RELIANCE"]


def test_symbols_outside_the_universe_are_dropped() -> None:
    assert map_symbols("Wipro and Infosys report", {"INFY"}) == ["INFY"]


def test_rss_dates_are_stored_in_utc() -> None:
    from datetime import datetime, timezone

    from intelligence_agents.news.rss import _parse_date

    fallback = datetime(2026, 10, 14, 18, 0, tzinfo=timezone.utc)
    parsed = _parse_date("Wed, 14 Oct 2026 23:00:00 +0530", fallback)
    assert parsed == datetime(2026, 10, 14, 17, 30, tzinfo=timezone.utc)
    assert parsed.isoformat().endswith("+00:00")
