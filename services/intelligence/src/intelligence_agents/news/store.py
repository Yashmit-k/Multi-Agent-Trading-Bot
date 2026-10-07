"""SQLite / in-memory news store. Append-only. Future-dated rows stay quarantined."""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from contracts.schemas.news_article import NewsArticle
from contracts.time import require_aware

logger = logging.getLogger(__name__)


@dataclass
class NewsInsertResult:
    inserted: bool
    quarantined: bool
    duplicate: bool
    dropped_empty_symbols: bool = False


class NewsStore(Protocol):
    def insert(self, article: NewsArticle, *, now: datetime) -> NewsInsertResult: ...
    def articles_for(self, symbol: str, as_of: datetime) -> list[NewsArticle]: ...
    def graduate_quarantine(self, now: datetime) -> int: ...
    def record_empty_symbol_drop(self, title: str = "") -> None: ...
    @property
    def dropped_empty_symbols(self) -> int: ...


def _row_to_article(row: sqlite3.Row) -> NewsArticle:
    return NewsArticle.model_validate(
        {
            "article_id": row["article_id"],
            "source": row["source"],
            "title": row["title"],
            "url": row["url"],
            "published_at": row["published_at"],
            "retrieved_at": row["retrieved_at"],
            "content_hash": row["content_hash"],
            "symbols": json.loads(row["symbols"]),
            "raw_text": row["raw_text"],
            "metadata": json.loads(row["metadata"]),
        }
    )


class SqliteNewsStore:
    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._dropped_empty_symbols = 0
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                article_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                published_at TEXT NOT NULL,
                retrieved_at TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                symbols TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                metadata TEXT NOT NULL,
                quarantined INTEGER NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_hash ON articles(content_hash)"
        )
        self._conn.commit()

    @property
    def dropped_empty_symbols(self) -> int:
        return self._dropped_empty_symbols

    def record_empty_symbol_drop(self, title: str = "") -> None:
        self._dropped_empty_symbols += 1
        logger.warning(
            "articles_dropped_empty_symbols",
            extra={"count": self._dropped_empty_symbols, "title": title[:80]},
        )

    def insert(self, article: NewsArticle, *, now: datetime) -> NewsInsertResult:
        aware_now = require_aware(now, "now")
        if not article.symbols:
            self.record_empty_symbol_drop(article.article_id)
            return NewsInsertResult(False, False, False, dropped_empty_symbols=True)
        existing = self._conn.execute(
            "SELECT 1 FROM articles WHERE article_id = ? OR content_hash = ?",
            (article.article_id, article.content_hash),
        ).fetchone()
        if existing is not None:
            return NewsInsertResult(False, False, True)
        quarantined = article.published_at > aware_now
        self._conn.execute(
            """
            INSERT INTO articles (
                article_id, source, title, url, published_at, retrieved_at,
                content_hash, symbols, raw_text, metadata, quarantined
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                article.article_id,
                article.source,
                article.title,
                str(article.url),
                article.published_at.isoformat(),
                article.retrieved_at.isoformat(),
                article.content_hash,
                json.dumps(list(article.symbols)),
                article.raw_text,
                json.dumps(article.metadata),
                int(quarantined),
            ),
        )
        self._conn.commit()
        return NewsInsertResult(True, quarantined, False)

    def articles_for(self, symbol: str, as_of: datetime) -> list[NewsArticle]:
        aware = require_aware(as_of, "as_of")
        as_of_iso = aware.isoformat()
        rows = self._conn.execute(
            """
            SELECT * FROM articles
            WHERE quarantined = 0
              AND published_at <= ?
              AND retrieved_at <= ?
            """,
            (as_of_iso, as_of_iso),
        ).fetchall()
        needle = symbol.strip().upper()
        articles: list[NewsArticle] = []
        for row in rows:
            article = _row_to_article(row)
            if needle in article.symbols:
                articles.append(article)
        return articles

    def graduate_quarantine(self, now: datetime) -> int:
        aware = require_aware(now, "now")
        cursor = self._conn.execute(
            "UPDATE articles SET quarantined = 0 WHERE quarantined = 1 AND published_at <= ?",
            (aware.isoformat(),),
        )
        self._conn.commit()
        return int(cursor.rowcount or 0)


@dataclass
class MemoryNewsStore:
    """Test-only in-memory store. Same PIT and quarantine rules."""

    _rows: list[tuple[NewsArticle, bool]] = field(default_factory=list)
    dropped_empty_symbols: int = 0

    def record_empty_symbol_drop(self, title: str = "") -> None:
        self.dropped_empty_symbols += 1
        logger.warning(
            "articles_dropped_empty_symbols",
            extra={"count": self.dropped_empty_symbols, "title": title[:80]},
        )

    def insert(self, article: NewsArticle, *, now: datetime) -> NewsInsertResult:
        aware_now = require_aware(now, "now")
        if not article.symbols:
            self.record_empty_symbol_drop(article.article_id)
            return NewsInsertResult(False, False, False, dropped_empty_symbols=True)
        if any(
            existing.article_id == article.article_id or existing.content_hash == article.content_hash
            for existing, _ in self._rows
        ):
            return NewsInsertResult(False, False, True)
        quarantined = article.published_at > aware_now
        self._rows.append((article, quarantined))
        return NewsInsertResult(True, quarantined, False)

    def articles_for(self, symbol: str, as_of: datetime) -> list[NewsArticle]:
        aware = require_aware(as_of, "as_of")
        needle = symbol.strip().upper()
        return [
            article
            for article, quarantined in self._rows
            if not quarantined
            and article.published_at <= aware
            and article.retrieved_at <= aware
            and needle in article.symbols
        ]

    def graduate_quarantine(self, now: datetime) -> int:
        aware = require_aware(now, "now")
        graduated = 0
        updated: list[tuple[NewsArticle, bool]] = []
        for article, quarantined in self._rows:
            if quarantined and article.published_at <= aware:
                updated.append((article, False))
                graduated += 1
            else:
                updated.append((article, quarantined))
        self._rows = updated
        return graduated
