"""LLM answer cache keyed by prompt version, content hash and model. Not used for BACKTEST reproducibility — FixtureLLM is.

With a path, answers also persist in SQLite, so a restart does not spend the provider's daily quota
again on news and fundamentals that have not changed.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict

from intelligence_agents.llm.types import LLMAssessment
from intelligence_agents.llm.types import PROMPT_VERSION

logger = logging.getLogger(__name__)


class LLMCache:
    def __init__(self, path: str | None = None) -> None:
        self._items: dict[tuple[str, str, str], LLMAssessment] = {}
        self.hits = 0
        self._conn: sqlite3.Connection | None = None
        if path:
            try:
                self._conn = sqlite3.connect(path, check_same_thread=False)
                self._conn.execute(
                    "CREATE TABLE IF NOT EXISTS llm_cache (prompt_version TEXT, content_hash TEXT, model TEXT, payload TEXT,"
                    " PRIMARY KEY (prompt_version, content_hash, model))"
                )
                self._conn.commit()
            except sqlite3.Error:
                logger.exception("llm_cache_unavailable")
                self._conn = None

    def get(self, content_hash: str, model: str) -> LLMAssessment | None:
        key = (PROMPT_VERSION, content_hash, model)
        value = self._items.get(key)
        if value is None and self._conn is not None:
            try:
                row = self._conn.execute(
                    "SELECT payload FROM llm_cache WHERE prompt_version = ? AND content_hash = ? AND model = ?", key
                ).fetchone()
            except sqlite3.Error:
                row = None
            if row is not None:
                data = json.loads(row[0])
                value = LLMAssessment(**{**data, "reason_codes": tuple(data["reason_codes"])})
                self._items[key] = value
        if value is not None:
            self.hits += 1
        return value

    def put(self, content_hash: str, model: str, assessment: LLMAssessment) -> None:
        key = (PROMPT_VERSION, content_hash, model)
        self._items[key] = assessment
        if self._conn is not None:
            try:
                self._conn.execute("INSERT OR REPLACE INTO llm_cache VALUES (?, ?, ?, ?)", (*key, json.dumps(asdict(assessment))))
                self._conn.commit()
            except sqlite3.Error:
                logger.warning("llm_cache_write_failed")
