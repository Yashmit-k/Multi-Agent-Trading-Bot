"""Build the catalog returned by GET /api/v1/system/contracts."""

from contracts.enums import AgentName, Horizon, TradingMode
from contracts.events import EventType
from contracts.registry import EXPORT_MODELS
from contracts.schemas.catalog import ContractCatalog
from contracts.version import SCHEMA_VERSION, __version__


def build_catalog() -> ContractCatalog:
    return ContractCatalog(
        contract_version=__version__,
        schema_versions={name: SCHEMA_VERSION for name in EXPORT_MODELS},
        event_versions={event_type.value: SCHEMA_VERSION for event_type in EventType},
        supported_agents=list(AgentName),
        supported_horizons=list(Horizon),
        supported_modes=list(TradingMode),
    )
