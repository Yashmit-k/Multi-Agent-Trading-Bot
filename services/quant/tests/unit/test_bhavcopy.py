"""Bhavcopy panel: securities chain across renames and splits; a reused symbol after a long gap is a new security."""

from __future__ import annotations

import io
import zipfile
from datetime import date, timedelta

import numpy as np

from quant_agents.research import bhavcopy as bc

HEAD = "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,\n"


def _day(folder, day: date, rows: list[tuple[str, str, float, float, str]]) -> None:
    text = HEAD + "".join(f"{s},{series},{c},{c},{c},{c},{c},{pc},1,1000,X,1,{isin},\n" for s, series, c, pc, isin in rows)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("bhav.csv", text)
    (folder / f"{day.isoformat()}.zip").write_bytes(buffer.getvalue())


def test_rename_split_and_reuse(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(bc, "RAW", tmp_path)
    d0 = date(2020, 1, 1)
    _day(tmp_path, d0, [("OLDNAME", "EQ", 100, 100, "INE1"), ("SPLITCO", "EQ", 1000, 1000, "INE2"), ("GONE", "EQ", 50, 50, "INE3")])
    _day(tmp_path, d0 + timedelta(1), [("NEWNAME", "EQ", 110, 100, "INE1"), ("SPLITCO", "EQ", 105, 100, "INE2X")])  # 1:10 split, new ISIN
    for k in range(2, 70):
        _day(tmp_path, d0 + timedelta(k), [("NEWNAME", "EQ", 110, 110, "INE1"), ("SPLITCO", "BE", 105, 105, "INE2X")])
    _day(tmp_path, d0 + timedelta(70), [("NEWNAME", "EQ", 110, 110, "INE1"), ("SPLITCO", "EQ", 105, 105, "INE2X"), ("GONE", "EQ", 10, 10, "INE9")])
    panel = bc.build()
    assert list(panel.symbols) == ["NEWNAME", "SPLITCO", "GONE", "GONE"]
    ret = panel.ret
    assert np.isclose(ret[1, 0], 0.10)  # rename kept one history
    assert np.isclose(ret[1, 1], 0.05)  # split: return from the adjusted previous close
    assert panel.series[5, 1] == 2  # BE keeps the price series
    assert np.isnan(panel.close[70, 2]) and panel.close[70, 3] == 10  # reused symbol: a new chain
