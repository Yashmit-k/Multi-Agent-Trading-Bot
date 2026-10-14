"""Fixture Intelligence over HTTP. Not live news and not the production stack.

The project is started from docker-compose.checkpoint4.yml only. If Docker is
unavailable the test fails as BLOCKED. It does not skip.
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from contracts.schemas.news_article import NewsArticle

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "docker-compose.checkpoint4.yml"
PROJECT = "dev3-cp4-intel"
BASE = "http://127.0.0.1:18101"


def test_fixture_news_matches_the_article_contract() -> None:
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "core-worker" not in text
    assert "docker-compose.yml" not in text
    assert "env_file" not in text
    assert "NEWS_RSS_URLS" not in text
    assert "INTELLIGENCE_DATA_SOURCE: fixtures" in text
    assert 'LLM_API_KEY: ""' in text
    assert "127.0.0.1:18101:8080" in text
    _compose("down", "-v")
    started = _compose("up", "-d", "--build")
    if started.returncode != 0:
        pytest.fail(f"BLOCKED: isolated intelligence project did not start:\n{started.stderr}")
    try:
        health = _get_json("/health")
        assert health["llm_mode"] == "fixture"
        assert health["status"] in {"ok", "degraded"}
        rows = _get_json("/news/RELIANCE")
        assert isinstance(rows, list) and rows
        articles = [NewsArticle.model_validate(item) for item in rows]
        assert all("RELIANCE" in item.symbols for item in articles)
        assert all(item.source == "fixture-wire" for item in articles)
    finally:
        _compose("down", "-v")


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "-f", str(COMPOSE_FILE), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _get_json(path: str) -> object:
    deadline = time.time() + 180
    last = "intelligence did not answer"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + path, timeout=3) as response:
                return json.load(response)
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(1)
    logs = _compose("logs", "--tail", "80", "intelligence")
    pytest.fail(f"BLOCKED: {last}\n{logs.stdout}\n{logs.stderr}")
