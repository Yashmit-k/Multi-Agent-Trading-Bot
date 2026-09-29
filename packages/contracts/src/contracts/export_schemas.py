"""Write JSON Schema and OpenAPI from the Pydantic models.

Run from the repo root:

    python -m contracts.export_schemas

Do not hand-edit files under docs/contracts.
"""

from __future__ import annotations

import json
from pathlib import Path

from contracts.api import app
from contracts.registry import EXPORT_MODELS
from contracts.schemas.event import EventEnvelope, event_envelope_json_schema


def repo_root() -> Path:
    start_points = [Path.cwd().resolve(), Path(__file__).resolve()]
    for start in start_points:
        for parent in [start, *start.parents]:
            marker = parent / "packages" / "contracts" / "pyproject.toml"
            if marker.is_file():
                return parent
    raise RuntimeError("could not find the repo root containing packages/contracts/pyproject.toml")


def render_documents() -> dict[str, str]:
    """Return relative docs/contracts paths and their canonical JSON text."""
    openapi = app.openapi()
    components = openapi.setdefault("components", {}).setdefault("schemas", {})
    documents: dict[str, str] = {}
    for name, model in EXPORT_MODELS.items():
        schema = event_envelope_json_schema() if model is EventEnvelope else model.model_json_schema()
        components.setdefault(name, schema)
        documents[f"schemas/{name}.json"] = _dump(schema)
    documents = {"openapi.json": _dump(openapi), **documents}
    return documents


def write_contracts(output_dir: Path | None = None) -> Path:
    destination = output_dir or (repo_root() / "docs" / "contracts")
    for relative, text in render_documents().items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return destination


def _dump(document: object) -> str:
    return json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"


def main() -> None:
    written = write_contracts()
    print(written)


if __name__ == "__main__":
    main()
