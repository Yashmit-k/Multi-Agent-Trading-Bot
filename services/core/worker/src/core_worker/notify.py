"""Operator notifications: a morning Zerodha login reminder and an end-of-day paper summary.

Delivered to Telegram (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID) and/or a Slack/Discord-style
webhook (ALERT_WEBHOOK_URL). With neither configured, nothing is sent. Each message goes out
at most once per IST day; what was sent is kept in user_settings["notify_state"], so a worker
restart does not resend it. A notification failure never affects paper trading.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from core_db.repository import CoreRepository

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
REMINDER_FIRST = time(8, 30)
REMINDER_URGENT = time(9, 10)
REMINDER_END = time(9, 15)
SUMMARY_AFTER = time(15, 35)
SUMMARY_END = time(23, 0)
STATE_KEY = "notify_state"


@dataclass(frozen=True)
class Notifier:
    telegram_token: str = ""
    telegram_chat: str = ""
    webhook: str = ""

    @classmethod
    def from_env(cls) -> "Notifier":
        return cls(os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", ""), os.environ.get("ALERT_WEBHOOK_URL", ""))

    @property
    def configured(self) -> bool:
        return bool((self.telegram_token and self.telegram_chat) or self.webhook)

    def send(self, text: str, *, urlopen=urllib.request.urlopen) -> bool:
        sent = False
        targets: list[tuple[str, dict]] = []
        if self.telegram_token and self.telegram_chat:
            targets.append((f"https://api.telegram.org/bot{self.telegram_token}/sendMessage", {"chat_id": self.telegram_chat, "text": text, "disable_web_page_preview": True}))
        if self.webhook:
            targets.append((self.webhook, {"text": text, "content": text}))
        for url, body in targets:
            request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urlopen(request, timeout=10):
                    sent = True
            except Exception as exc:  # noqa: BLE001 - never let a notification break the worker
                logger.warning("notify_failed target=%s error_type=%s", "telegram" if "telegram" in url else "webhook", type(exc).__name__)
        return sent


def _token_valid(repository: CoreRepository, now: datetime) -> bool:
    """Kite tokens expire at 06:00 IST: valid only if issued after the latest 06:00."""
    local = now.astimezone(IST)
    cutoff = local.replace(hour=6, minute=0, second=0, microsecond=0)
    if local < cutoff:
        cutoff -= timedelta(days=1)
    return repository.broker_token("zerodha", not_before=cutoff.astimezone(timezone.utc)) is not None


def _trading_day(day: date) -> bool:
    from core_paper.trading_calendar import session_for

    try:
        return session_for(day) is not None
    except Exception:  # noqa: BLE001 - outside calendar coverage
        return day.weekday() < 5


def _state(repository: CoreRepository) -> dict:
    stored = repository.get_setting(STATE_KEY)
    return dict(stored["payload"]) if stored else {}


def _mark(repository: CoreRepository, state: dict, key: str, day: date, now: datetime) -> None:
    repository.save_setting(STATE_KEY, {**state, key: day.isoformat()}, updated_by="worker", now=now)


def _rupees(value: object) -> str:
    amount = Decimal(str(value))
    sign = "-" if amount < 0 else "+"
    return f"{sign}Rs {abs(amount):,.0f}"


def summary_text(repository: CoreRepository, day: date, now: datetime, site: str = "") -> str | None:
    from core_paper.daily import book_for_day

    book = repository.active_paper_session()
    if book is None or book.starting_cash is None:
        return None
    today = book_for_day(repository, book.starting_cash, day)
    if today is None:
        return f"StockX paper summary {day:%a %d %b}: no positions and no fills today."
    previous = [row for row in repository.list_daily_equity(book.session_id) if row["trading_day"] < day.isoformat()]
    day_pnl = Decimal(today["total_pnl"]) - (Decimal(previous[-1]["total_pnl"]) if previous else Decimal("0"))
    fills = [item for item in repository.list_executions() if item.executed_at.astimezone(IST).date() == day]
    sides = {order.order_id: order.side.value for order in repository.list_orders()} if fills else {}
    lines = [
        f"StockX paper summary {day:%a %d %b}",
        f"Equity Rs {Decimal(today['equity']):,.0f}  |  today {_rupees(day_pnl)}  |  total {_rupees(today['total_pnl'])}",
        f"Realized {_rupees(today['realized_pnl'])}, unrealized {_rupees(today['unrealized_pnl'])}, charges today Rs {Decimal(today['fees_today']):,.0f}",
        f"Open positions: {today['open_positions']}" + (f" ({', '.join(sorted(today['marks']))})" if today["marks"] else ""),
    ]
    if fills:
        lines.append(f"Fills today ({len(fills)}):")
        for item in sorted(fills, key=lambda fill: fill.executed_at)[:12]:
            lines.append(f"  {sides.get(item.order_id, '?')} {item.quantity} {item.symbol} @ {item.price} ({item.executed_at.astimezone(IST):%H:%M})")
    else:
        lines.append("No fills today.")
    if site:
        lines.append(site.rstrip("/") + "/journal")
    return "\n".join(lines)


def maybe_notify(repository: CoreRepository, notifier: Notifier, now: datetime, *, site: str = "", health_problems=None) -> list[str]:  # type: ignore[no-untyped-def]
    """Send whatever is due right now. Returns the keys sent (for logs and tests)."""
    if not notifier.configured:
        return []
    local = now.astimezone(IST)
    day = local.date()
    if not _trading_day(day):
        return []
    state = _state(repository)
    sent: list[str] = []
    clock = local.time()
    if REMINDER_FIRST <= clock < REMINDER_END and not _token_valid(repository, now):
        key = "reminder_urgent" if clock >= REMINDER_URGENT else "reminder"
        if state.get(key) != day.isoformat():
            urgent = key == "reminder_urgent"
            text = (
                ("URGENT: " if urgent else "")
                + f"StockX: Zerodha is not logged in for today ({day:%a %d %b}). Log in before 09:15 IST or the market data goes stale and no entries are placed."
            )
            if notifier.send(text):
                _mark(repository, state, key, day, now)
                state[key] = day.isoformat()
                sent.append(key)
    if SUMMARY_AFTER <= clock < SUMMARY_END and state.get("summary") != day.isoformat():
        text = summary_text(repository, day, now, site)
        if text is not None:
            problems = health_problems() if callable(health_problems) else (health_problems or [])
            if problems:
                text += "\nNeeds attention: " + "; ".join(problems[:5])
            if notifier.send(text):
                _mark(repository, state, "summary", day, now)
                sent.append("summary")
    return sent


def health_problems_from_api(base_url: str, token: str, *, urlopen=urllib.request.urlopen):  # type: ignore[no-untyped-def]
    """A callable listing non-ok health components, for the summary. Empty if the API cannot be read."""

    def read() -> list[str]:
        request = urllib.request.Request(base_url.rstrip("/") + "/api/v1/system/health", headers={"Authorization": f"Bearer {token}"})
        try:
            with urlopen(request, timeout=10) as response:
                checks = json.loads(response.read()).get("checks", [])
        except Exception:  # noqa: BLE001
            return []
        return [f"{item['component']}: {item['detail']}" for item in checks if item.get("status") in ("warn", "down")]

    return read
