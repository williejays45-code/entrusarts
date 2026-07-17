from dataclasses import dataclass
from typing import List
from era.acquisition.connector_enums import LegalClassification, ConnectorStatus, ConnectorCategory
@dataclass(frozen=True)
class ConnectorMetadata:
    connector_id: str
    provider_name: str
    version: str
    category: ConnectorCategory
    legal_classification: LegalClassification
    status: ConnectorStatus
    capabilities: List[str]
    refresh_schedule_hours: int
    rate_limit_per_day: int
    cache_duration_hours: int
    monthly_budget_limit: float | None
    max_requests: int
    max_retries: int
    retry_delay_seconds: int
