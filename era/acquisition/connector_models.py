from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List
from era.acquisition.connector_enums import LegalClassification, ConnectorStatus, ConnectorCategory
def utc_now():
    return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class ResourcePolicy:
    refresh_schedule_hours: int
    rate_limit_per_day: int
    cache_duration_hours: int
    monthly_budget_limit: float | None
    max_requests: int
@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int
    retry_delay_seconds: int
@dataclass(frozen=True)
class ConnectorRecord:
    connector_id: str
    provider_name: str
    version: str
    category: ConnectorCategory
    legal_classification: LegalClassification
    status: ConnectorStatus
    capabilities: List[str]
    resource_policy: ResourcePolicy
    retry_policy: RetryPolicy
    last_success: str | None = None
    last_failure: str | None = None
    consecutive_failures: int = 0
    average_response_time_ms: int | None = None
    success_count: int = 0
    failure_count: int = 0
    success_rate: float | None = None
    created_at: str = field(default_factory=utc_now)
