"""NSE capital-market bhavcopies -> one dense daily panel (services/quant/docs/whole-market-protocol.md).

A security is chained from one day to the next by ISIN, or else by symbol, so a rename (same ISIN) or a split
(new ISIN, same symbol) keeps one history. Returns are CLOSE / PREVCLOSE - 1: NSE adjusts PREVCLOSE on ex-dates.

    python -m quant_agents.research.bhavcopy      # build datasets/research/bhavcopy/panel.npz
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

from quant_agents.research import exit_rules as er

RAW = er.ROOT / "datasets/research/bhavcopy/raw"
PANEL = er.ROOT / "datasets/research/bhavcopy/panel.npz"
SERIES = {"EQ": 1, "BE": 2, "BZ": 2}
OLD = ("SYMBOL", "SERIES", "OPEN", "HIGH", "LOW", "CLOSE", "PREVCLOSE", "TOTTRDVAL", "ISIN")
STALE = 60
NEW = ("TckrSymb", "SctySrs", "OpnPric", "HghPric", "LwPric", "ClsPric", "PrvsClsgPric", "TtlTrfVal", "ISIN")


def rows(path: Path) -> list[tuple[str, int, float, float, float, float, float, float, str]]:
    with zipfile.ZipFile(path) as archive:
        text = archive.read(archive.namelist()[0]).decode("utf-8", "replace")
    reader = csv.DictReader(io.StringIO(text))
    names = NEW if "TckrSymb" in (reader.fieldnames or []) else OLD
    out = []
    for r in reader:
        series = SERIES.get((r.get(names[1]) or "").strip())
        if series is None:
            continue
        try:
            o, h, l, c, pc, v = (float(r[k]) for k in names[2:8])
        except (TypeError, ValueError):
            continue
        if c <= 0 or pc <= 0:
            continue
        out.append((r[names[0]].strip(), series, o, h, l, c, pc, v, (r.get(names[8]) or "").strip()))
    return out


@dataclass
class Panel:
    days: np.ndarray  # ordinals
    symbols: np.ndarray  # last symbol of each chain
    etf: np.ndarray  # bool per chain
    series: np.ndarray  # days x chains: 0 none, 1 EQ, 2 BE/BZ
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    prev: np.ndarray
    value: np.ndarray

    @property
    def ret(self) -> np.ndarray:
        with np.errstate(invalid="ignore", divide="ignore"):
            return self.close / self.prev - 1


def build(folder: Path | None = None) -> Panel:
    files = sorted((folder or RAW).glob("*.zip"))
    by_isin: dict[str, int] = {}
    by_symbol: dict[str, int] = {}
    symbols: list[str] = []
    etf: list[bool] = []
    last_seen: list[int] = []
    daily = []
    for k_day, path in enumerate(files):
        today_isin: dict[str, int] = {}
        today_symbol: dict[str, int] = {}
        used: set[int] = set()
        entries = []
        for symbol, series, o, h, l, c, pc, v, isin in rows(path):
            chain = by_isin.get(isin) if isin else None
            if chain is None:
                chain = by_symbol.get(symbol)
                if chain is not None and k_day - last_seen[chain] > STALE:
                    chain = None  # a symbol reused by another company after a long gap
            if chain is None or chain in used:
                chain = len(symbols)
                symbols.append(symbol)
                etf.append(isin.startswith("INF"))
                last_seen.append(k_day)
            used.add(chain)
            last_seen[chain] = k_day
            symbols[chain] = symbol
            if isin:
                today_isin[isin] = chain
            today_symbol[symbol] = chain
            entries.append((chain, series, o, h, l, c, pc, v))
        by_isin.update(today_isin)
        by_symbol.update(today_symbol)
        daily.append((date.fromisoformat(path.stem).toordinal(), entries))
    n, m = len(daily), len(symbols)
    fields = {name: np.full((n, m), np.nan, dtype=np.float32) for name in ("open", "high", "low", "close", "prev", "value")}
    series = np.zeros((n, m), dtype=np.int8)
    for k, (_, entries) in enumerate(daily):
        for chain, s, o, h, l, c, pc, v in entries:
            series[k, chain] = s
            for name, x in zip(("open", "high", "low", "close", "prev", "value"), (o, h, l, c, pc, v)):
                fields[name][k, chain] = x
    return Panel(np.array([d for d, _ in daily]), np.array(symbols), np.array(etf), series, **fields)


def save(panel: Panel, path: Path | None = None) -> None:
    np.savez_compressed(path or PANEL, **{k: getattr(panel, k) for k in ("days", "symbols", "etf", "series", "open", "high", "low", "close", "prev", "value")})


def load(path: Path | None = None) -> Panel:
    z = np.load(path or PANEL, allow_pickle=False)
    return Panel(**{k: z[k] for k in z.files})


UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"
UDIFF_FROM = date(2024, 7, 8)


def url_for(day: date) -> str:
    if day < UDIFF_FROM:
        return f"https://nsearchives.nseindia.com/content/historical/EQUITIES/{day.year}/{day.strftime('%b').upper()}/cm{day.strftime('%d%b%Y').upper()}bhav.csv.zip"
    return f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{day.strftime('%Y%m%d')}_F_0000.csv.zip"


def fetch_day(day: date, folder: Path, *, timeout: float = 30.0) -> bool | None:
    """Download one day's bhavcopy into folder/<date>.zip. True: saved; False: NSE has no file (404); None: other failure."""
    import urllib.error
    import urllib.request

    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{day.isoformat()}.zip"
    try:
        with urllib.request.urlopen(urllib.request.Request(url_for(day), headers={"User-Agent": UA}), timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        return False if exc.code == 404 else None
    except Exception:  # noqa: BLE001 - network trouble: retried by the caller
        return None
    if not body.startswith(b"PK"):
        return None
    target.write_bytes(body)
    return True


if __name__ == "__main__":
    built = build()
    save(built)
    print("days", len(built.days), "chains", len(built.symbols), date.fromordinal(int(built.days[0])), date.fromordinal(int(built.days[-1])))
