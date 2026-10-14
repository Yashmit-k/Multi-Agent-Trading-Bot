"""One scoring pass. Run from the repository root after the protocol is frozen."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from quant_agents.research.daily_rules.evaluate import score_rules
from quant_agents.research.timesfm3.candles import load_closes
from quant_agents.research.timesfm3.scores import EXCLUDED_SYMBOL, official_session_date

NO_EDGE = "no tradable daily-rule edge under CNC costs."


def series_from_closes(points) -> dict[str, tuple[tuple[date, Decimal], ...]]:
    grouped: dict[str, list[tuple[date, Decimal]]] = {}
    for point in points:
        if point.symbol == EXCLUDED_SYMBOL:
            continue
        session = official_session_date(point.end)
        if session is None:
            continue
        grouped.setdefault(point.symbol, []).append((session, point.close))
    return {symbol: tuple(rows) for symbol, rows in grouped.items()}


def render(results) -> str:
    lines = [
        "# Daily rule result",
        "",
        "Scored once from `services/quant/docs/daily-rules-protocol.md`. No model was fit.",
        "",
        "| horizon | rule | windows | mean return | mean excess vs buy-and-hold | lower | upper | fraction selected | pass |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in results:
        lines.append(
            f"| {item.horizon} | {item.rule} | {item.sessions} | {item.mean_return} | {item.mean_excess} | {item.lower} | {item.upper} | {item.average_selected_fraction} | {item.passed} |"
        )
    passed = [item for item in results if item.passed]
    lines.extend(["", "Passed rules: " + (", ".join(f"{item.rule} H={item.horizon}" for item in passed) if passed else "none."), ""])
    if not passed:
        lines.append(NO_EDGE)
    lines.append("")
    return "\n".join(lines)


def write_report(path: Path | None = None) -> Path:
    target = path or Path(__file__).resolve().parents[4] / "docs" / "daily-rules-result.md"
    results = score_rules(series_from_closes(load_closes()))
    target.write_text(render(results), encoding="utf-8")
    return target


def main() -> None:
    print(write_report())


if __name__ == "__main__":
    main()
