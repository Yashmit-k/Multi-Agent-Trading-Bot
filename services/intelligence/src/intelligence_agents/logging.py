"""JSON logging. Never attach secrets."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

_SECRET_KEYS = frozenset(
    {
        "api_key",
        "llm_api_key",
        "internal_signal_token",
        "access_token",
        "password",
        "authorization",
        "token",
    }
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in logging.LogRecord("", 0, "", 0, None, None, None).__dict__
            and key not in {"message", "msg", "args"}
            and key.lower() not in _SECRET_KEYS
        }
        if extras:
            payload["extra"] = extras
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
