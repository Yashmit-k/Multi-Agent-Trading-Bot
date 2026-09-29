"""Payloads for system.alert and agent.heartbeat."""

from enum import StrEnum

from pydantic import AwareDatetime

from contracts.enums import AgentName
from contracts.schemas.common import ContractModel, JsonObject, NonEmptyStr


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SystemAlert(ContractModel):
    """Operational alert published on system.events."""

    alert_id: NonEmptyStr
    severity: AlertSeverity
    message: NonEmptyStr
    timestamp: AwareDatetime
    metadata: JsonObject


class AgentHeartbeat(ContractModel):
    """Liveness record from one canonical agent."""

    agent_name: AgentName
    agent_version: NonEmptyStr
    timestamp: AwareDatetime
    metadata: JsonObject
