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
    # Agent BUYs need at least this fused signal and confidence (exits keep the decision engine's 0.2 / 0.3).
    min_entry_signal: Decimal = Decimal("0.35")
    min_entry_confidence: Decimal = Decimal("0.4")
    stop_loss_pct: Decimal = Decimal("2")
    take_profit_pct: Decimal = Decimal("4")
    # Trade-level checks on every new BUY (core_risk.trade).
    max_daily_loss_pct: Decimal = Decimal("2")
    max_drawdown_pct: Decimal = Decimal("10")
    max_risk_per_trade_pct: Decimal = Decimal("1")
    min_reward_risk: Decimal = Decimal("1")
    max_price_drift_pct: Decimal = Decimal("3")
    stop_cooldown_hours: int = 24
    block_fallback_evidence: bool = True
    auto_entries: bool = True  # False: agents may still exit holdings, but only manual orders open new ones
    # Intraday (5-minute) agent entries. Off by default since the exit-rules study (2026-10-15): the fused
    # 5-minute signal flips within minutes and each round trip loses about 0.4% to charges.
    intraday_auto_entries: bool = False
    # Swing only (the default): the worker decides on daily bars alone and skips the intraday and long-term horizons.
    # Intraday stays in the code as future scope; turn this off (and intraday_auto_entries on) to bring it back.
    swing_only: bool = True
    # The LLM portfolio manager reviews each agent BUY before risk: approve, shrink or veto (never enlarge).
    manager_review: bool = True
    # How an applied Strategy-lab strategy and the agents share the book:
    # replace = only the strategy opens trades; alongside = both open trades independently;
    # agents_agree = only the strategy opens trades, and only when the agents' fused view is not bearish.
    strategy_mode: str = "replace"
    # How agent swing BUYs are decided: "fusion" = one confidence-weighted average of the agents;
    # "specialists" = each agent has one job (trigger, confirm, event check, ...), see core_decision.specialists.
    decision_mode: str = "fusion"
    # agents_agree mode: the agents whose view a strategy entry must not contradict, comma-separated. A dip-buyer
    # cares whether there is bad news, not whether the trend is down, so the trend agents are left out by default.
    agree_agents: str = "news,earnings"

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
    "min_entry_signal": (Decimal("0.2"), Decimal("1"), "Minimum fused signal for an agent buy"),
    "min_entry_confidence": (Decimal("0.3"), Decimal("1"), "Minimum fused confidence for an agent buy"),
    "stop_loss_pct": (Decimal("0.5"), Decimal("20"), "Stop loss (%)"),
    "take_profit_pct": (Decimal("0.5"), Decimal("50"), "Take profit (%)"),
    "max_daily_loss_pct": (Decimal("0.1"), Decimal("20"), "Daily loss limit (% of starting cash)"),
    "max_drawdown_pct": (Decimal("1"), Decimal("50"), "Drawdown limit (% below peak)"),
    "max_risk_per_trade_pct": (Decimal("0.05"), Decimal("10"), "Loss at the stop per trade (% of starting cash)"),
    "min_reward_risk": (Decimal("0"), Decimal("10"), "Minimum target ÷ stop distance"),
    "max_price_drift_pct": (Decimal("0.2"), Decimal("20"), "Price drift since the signal (%)"),
    "stop_cooldown_hours": (Decimal("0"), Decimal("240"), "No re-entry after a stop-out (hours)"),
}

CHOICES: dict[str, tuple[tuple[str, str], ...]] = {
    "decision_mode": (
        ("fusion", "Fusion: one weighted average of the agents"),
        ("specialists", "Specialists: each agent has one job"),
    ),
    "strategy_mode": (
        ("replace", "Strategy replaces the agents"),
        ("alongside", "Strategy and agents both trade"),
        ("agents_agree", "Strategy trades only when the agents agree"),
    ),
}

# Agents that may be named in agree_agents (each votes with weight 1 in the agents_agree check).
AGREE_AGENT_CHOICES: tuple[tuple[str, str], ...] = (
    ("technical", "Technical"),
    ("momentum", "Momentum"),
    ("mean_reversion", "Mean reversion"),
    ("volume", "Volume"),
    ("regime", "Market regime"),
    ("news", "News"),
    ("fundamental", "Fundamental"),
    ("valuation", "Valuation"),
    ("earnings", "Earnings"),
)

DEFAULTS = RiskSettings()


def parse_agree_agents(raw: object) -> str:
    """'news, Earnings' -> 'news,earnings'. Raises ValueError for an unknown name or an empty list."""
    if not isinstance(raw, str):
        raise ValueError("must be a comma-separated list of agent names")
    allowed = [value for value, _ in AGREE_AGENT_CHOICES]
    names: list[str] = []
    for part in raw.split(","):
        name = part.strip().lower()
        if not name:
            continue
        if name not in allowed:
            raise ValueError(f"unknown agent {name!r}; choose from {', '.join(allowed)}")
        if name not in names:
            names.append(name)
    if not names:
        raise ValueError("choose at least one agent")
    return ",".join(names)


def agree_agent_names(settings: object) -> tuple[str, ...]:
    """The agree_agents setting as a tuple, falling back to the default for an old settings object."""
    return tuple(getattr(settings, "agree_agents", DEFAULTS.agree_agents).split(","))


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
            if key == "agree_agents":
                values[key] = parse_agree_agents(raw)
                continue
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
        {"key": "swing_only", "label": "Swing trading only (daily bars; intraday is future scope)", "min": None, "max": None, "default": "true"},
        {"key": "intraday_auto_entries", "label": "Agents may open intraday (5-minute) positions", "min": None, "max": None, "default": "false"},
        {"key": "block_fallback_evidence", "label": "Block buys backed only by fallback heuristics", "min": None, "max": None, "default": "true"},
        {"key": "manager_review", "label": "Portfolio manager reviews agent buys", "min": None, "max": None, "default": "true"},
        {"key": "decision_mode", "label": "How agent buys are decided", "min": None, "max": None, "default": DEFAULTS.decision_mode,
         "choices": [{"value": value, "label": label} for value, label in CHOICES["decision_mode"]]},
        {"key": "strategy_mode", "label": "Applied strategy and the agents", "min": None, "max": None, "default": DEFAULTS.strategy_mode,
         "choices": [{"value": value, "label": label} for value, label in CHOICES["strategy_mode"]]},
        {"key": "agree_agents", "label": "Agents a strategy must agree with", "min": None, "max": None, "default": DEFAULTS.agree_agents,
         "multiple": True, "choices": [{"value": value, "label": label} for value, label in AGREE_AGENT_CHOICES]},
    ]
