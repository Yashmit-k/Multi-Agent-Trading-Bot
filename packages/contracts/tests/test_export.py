"""Checked-in JSON Schema and OpenAPI stay generated."""

from contracts.export_schemas import render_documents, repo_root


def test_checked_in_contracts_match_generator() -> None:
    destination = repo_root() / "docs" / "contracts"
    for relative, text in render_documents().items():
        assert (destination / relative).read_text(encoding="utf-8") == text
