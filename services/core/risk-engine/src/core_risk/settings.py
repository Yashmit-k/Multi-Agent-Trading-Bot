"""User-editable paper risk settings, with hard bounds the UI cannot exceed.

The worker reads these every cycle, so a change applies from the next cycle. Defaults are the
values the system ran with before settings existed. Every value is bounded: a typo cannot turn
the paper book into something unbounded.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from decimal import Decimal, InvalidOperation

HARD_MAX_ORDER_NOTIONAL = Decimal("100000")


@dataclass(frozen=True)
class RiskSettings:
    max_order_notional: Decimal = Decimal("20000")
    daily_entry_limit: int = 6
    max_open_positions: int = 10
    max_per_sector: int = 2
    max_exposure_fraction: Decimal = Decimal("0.30")
    max_per_stock: Decimal = Decimal("40000")
    stop_loss_pct: Decimal = Decimal("2")
    take_profit_pct: Decimal = Decimal("4")
    auto_entries: bool = True  # False: agents may still exit holdings, but only manual orders open new ones
    # Intraday (5-minute) agent entries. Off by default since the exit-rules study (2026-10-15): the fused
    # 5-minute signal flips within minutes and each round trip loses about 0.4% to charges.
    intraday_auto_entries: bool = False
    # The LLM portfolio manager reviews each agent BUY before risk: approve, shrink or veto (never enlarge).
    manager_review: bool = True
    # How an applied Strategy-lab strategy and the agents share the book:
    # replace = only the strategy opens trades; alongside = both open trades independently;
    # agents_agree = only the strategy opens trades, and only when the agents' fused view is not bearish.
    strategy_mode: str = "replace"

    def as_json(self) -> dict[str, object]:
        return {key: (str(value) if isinstance(value, Decimal) else value) for key, value in asdict(self).items()}


# (minimum, maximum, label) per field. Money in rupees, fractions 0-1, percentages 0-100.
BOUNDS: dict[str, tuple[Decimal, Decimal, str]] = {
    "max_order_notional": (Decimal("1000"), HARD_MAX_ORDER_NOTIONAL, "Per-order limit (Rs)"),
    "daily_entry_limit": (Decimal("0"), Decimal("50"), "New entries per day"),
    "max_open_positions": (Decimal("1"), Decimal("50"), "Open positions"),
    "max_per_sector": (Decimal("1"), Decimal("50"), "Positions per sector"),
    "max_exposure_fraction": (Decimal("0.01"), Decimal("1"), "Total exposure (fraction of starting cash)"),
    "max_per_stock": (Decimal("1000"), Decimal("500000"), "Money in one stock (Rs)"),
    "stop_loss_pct": (Decimal("0.5"), Decimal("20"), "Stop loss (%)"),
    "take_profit_pct": (Decimal("0.5"), Decimal("50"), "Take profit (%)"),
}

CHOICES: dict[str, tuple[tuple[str, str], ...]] = {
    "strategy_mode": (
        ("replace", "Strategy replaces the agents"),
        ("alongside", "Strategy and agents both trade"),
        ("agents_agree", "Strategy trades only when the agents agree"),
    ),
}

DEFAULTS = RiskSettings()


class SettingsError(ValueError):
    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__("; ".join(f"{key}: {value}" for key, value in errors.items()))
        self.errors = errors


def parse_settings(payload: dict[str, object] | None, *, strict: bool = True) -> RiskSettings:
    """Stored or submitted values over the defaults. strict=False drops bad stored values instead of raising."""
    values: dict[str, object] = {}
    errors: dict[str, str] = {}
    known = {item.name: item for item in fields(RiskSettings)}
    for key, raw in (payload or {}).items():
        if key not in known:
            if strict:
                errors[key] = "unknown setting"
            continue
        default = getattr(DEFAULTS, key)
        try:
            if key in CHOICES:
                allowed = [value for value, _ in CHOICES[key]]
                if raw not in allowed:
                    raise ValueError(f"must be one of {', '.join(allowed)}")
                values[key] = raw
                continue
            if isinstance(default, bool):
                if not isinstance(raw, bool):
                    raise ValueError("must be true or false")
                values[key] = raw
                continue
            number = Decimal(str(raw))
            if not number.is_finite():
                raise ValueError("must be a number")
            if isinstance(default, int):
                if number != number.to_integral_value():
                    raise ValueError("must be a whole number")
                number = number.to_integral_value()
            low, high, _ = BOUNDS[key]
            if number < low or number > high:
                raise ValueError(f"must be between {low} and {high}")
            values[key] = int(number) if isinstance(default, int) else number
        except (ValueError, InvalidOperation) as exc:
            errors[key] = str(exc) if str(exc) else "invalid"
    if errors and strict:
        raise SettingsError(errors)
    return RiskSettings(**{**asdict(DEFAULTS), **values})


def describe_bounds() -> list[dict[str, object]]:
    return [
        {"key": key, "label": label, "min": str(low), "max": str(high), "default": str(getattr(DEFAULTS, key))}
        for key, (low, high, label) in BOUNDS.items()
    ] + [
        {"key": "auto_entries", "label": "Agents may open new positions", "min": None, "max": None, "default": "true"},
        {"key": "intraday_auto_entries", "label": "Agents may open intraday (5-minute) positions", "min": None, "max": None, "default": "false"},
        {"key": "manager_review", "label": "Portfolio manager reviews agent buys", "min": None, "max": None, "default": "true"},
        {"key": "strategy_mode", "label": "Applied strategy and the agents", "min": None, "max": None, "default": DEFAULTS.strategy_mode,
         "choices": [{"value": value, "label": label} for value, label in CHOICES["strategy_mode"]]},
    ]
