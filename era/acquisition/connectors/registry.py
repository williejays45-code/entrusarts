from era.acquisition.source_reliability_registry import SourceReliabilityRegistry
from era.acquisition.connector_models import ConnectorRecord, ResourcePolicy, RetryPolicy
from era.acquisition.connectors import registry_errors as errors
class ConnectorRegistryWrapper:
    """
    Thin acquisition-layer wrapper around SRR-001.
    This class does not own connector state.
    This class does not maintain a parallel registry.
    SRR-001 remains the single source of truth.
    """
    def __init__(self, source_registry: SourceReliabilityRegistry):
        self.source_registry = source_registry
    def register_metadata(self, metadata):
        if metadata is None:
            return errors.CONNECTOR_METADATA_REQUIRED, None
        connector = ConnectorRecord(
            connector_id=metadata.connector_id,
            provider_name=metadata.provider_name,
            version=metadata.version,
            category=metadata.category,
            legal_classification=metadata.legal_classification,
            status=metadata.status,
            capabilities=metadata.capabilities,
            resource_policy=ResourcePolicy(
                refresh_schedule_hours=metadata.refresh_schedule_hours,
                rate_limit_per_day=metadata.rate_limit_per_day,
                cache_duration_hours=metadata.cache_duration_hours,
                monthly_budget_limit=metadata.monthly_budget_limit,
                max_requests=metadata.max_requests,
            ),
            retry_policy=RetryPolicy(
                max_retries=metadata.max_retries,
                retry_delay_seconds=metadata.retry_delay_seconds,
            ),
        )
        status, registered = self.source_registry.register_connector(connector)
        if registered is None:
            return status, None
        return errors.PASS, registered
    def get_connector(self, connector_id: str):
        return self.source_registry.get_connector(connector_id)
    def enable_connector(self, connector_id: str):
        return self.source_registry.enable_connector(connector_id)
    def disable_connector(self, connector_id: str):
        return self.source_registry.disable_connector(connector_id)
    def forbidden_parallel_registry_write(self):
        return False, errors.PARALLEL_REGISTRY_FORBIDDEN
