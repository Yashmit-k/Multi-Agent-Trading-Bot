"""Write the 2024 zero-shot comparison. Does not fine-tune or open the holdout."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from quant_agents.research.timesfm3.candles import load_closes
from quant_agents.research.timesfm3.forecast import median_forecasts
from quant_agents.research.timesfm3.scores import (
    SCORE_YEAR,
    decision_rows,
    flat_mean_net,
    last_close_forecasts,
    score_forecasts,
)


def write_report(destination: Path) -> str:
    rows = decision_rows(load_closes(), year=SCORE_YEAR)
    if not rows:
        raise RuntimeError("no 2024 decision rows")
    model = score_forecasts(rows, median_forecasts(rows))
    naive = score_forecasts(rows, last_close_forecasts(rows))
    flat = flat_mean_net(rows)
    hit = "n/a" if model.hit_rate is None else f"{model.hit_rate}"
    trade_mean = "n/a" if model.mean_net_trades is None else f"{model.mean_net_trades}"
    text = "\n".join(
        [
            "# TimesFM-3 2024 zero-shot report",
            "",
            "Zero-shot median forecast of the next 2024 session close. Not a paper signal. 2025 and the holdout were not scored.",
            "",
            f"- Scored rows: {model.scored}",
            f"- TimesFM sign hit rate: {hit} ({model.hits} / {model.nonzero_realized})",
            f"- TimesFM trades: {model.trade_count}",
            f"- TimesFM mean net, all rows: {model.mean_net_all}",
            f"- TimesFM mean net, trades: {trade_mean}",
            f"- TimesFM mean absolute price error: {model.mean_price_error}",
            f"- Always-flat mean net: {flat}",
            f"- Last-close sign hit rate: {naive.hit_rate}",
            f"- Last-close mean net: {naive.mean_net_all}",
            f"- Last-close mean absolute price error: {naive.mean_price_error}",
            "",
            _comparison(model.mean_net_all, flat, model.mean_price_error, naive.mean_price_error),
            "",
        ]
    )
    destination.write_text(text, encoding="utf-8")
    return text


def _comparison(model_net: Decimal, flat_net: Decimal, model_error: Decimal, naive_error: Decimal) -> str:
    price = (
        "TimesFM's mean absolute price error is smaller than last-close."
        if model_error < naive_error
        else "TimesFM's mean absolute price error is larger than last-close."
    )
    return (
        f"Mean net after 2 bp is {model_net}, against an always-flat mean of {flat_net}. "
        "Last-close predicts a zero sign, so its hit rate is 0 by construction and is not evidence of an edge. "
        f"Compare the absolute price errors above. A smaller TimesFM error would be the path-forecast win. {price} "
        "This report does not authorize fine-tuning or a paper signal."
    )


def main() -> None:
    destination = Path(__file__).resolve().parents[4] / "docs" / "timesfm3-2024-report.md"
    print(write_report(destination))


if __name__ == "__main__":
    main()
