"""Export OpenAPI for frontend generation."""

from __future__ import annotations

import json
from pathlib import Path

from app import app

if __name__ == "__main__":
    Path(__file__).with_name("openapi.json").write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
