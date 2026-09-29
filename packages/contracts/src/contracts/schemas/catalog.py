"""Response body for GET /api/v1/system/contracts."""

from contracts.enums import AgentName, Horizon, TradingMode
from contracts.schemas.common import ContractModel, NonEmptyStr


class ContractCatalog(ContractModel):
    """Versions and closed vocabularies shipped by this package."""

    contract_version: NonEmptyStr
    schema_versions: dict[str, NonEmptyStr]
    event_versions: dict[str, NonEmptyStr]
    supported_agents: list[AgentName]
    supported_horizons: list[Horizon]
    supported_modes: list[TradingMode]
