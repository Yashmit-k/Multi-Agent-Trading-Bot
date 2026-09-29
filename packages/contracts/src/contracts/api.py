"""Reference HTTP contract. This app validates payloads and does not trade."""

from fastapi import FastAPI

from contracts.catalog import build_catalog
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.catalog import ContractCatalog
from contracts.schemas.submission import SubmissionResult
from contracts.version import __version__


def create_app() -> FastAPI:
    app = FastAPI(
        title="Multi-agent trading contracts",
        version=__version__,
        summary="Canonical internal contracts. This app validates schemas and does not trade.",
    )

    @app.post("/api/v1/internal/signals", response_model=SubmissionResult)
    def submit_signal(signal: AgentSignal) -> SubmissionResult:
        """Validate an AgentSignal. Core owns persistence and fan-out."""
        return SubmissionResult(
            accepted=True,
            signal_id=signal.signal_id,
            duplicate=False,
            message="accepted",
        )

    @app.get("/api/v1/system/contracts", response_model=ContractCatalog)
    def read_contracts() -> ContractCatalog:
        """Return package version, schema versions, and closed vocabularies."""
        return build_catalog()

    return app


app = create_app()
