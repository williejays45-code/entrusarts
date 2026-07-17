from dataclasses import replace, asdict
from era.acquisition.connector_audit import AcquisitionAuditPublisher
from era.acquisition.connector_enums import (
    LegalClassification,
    ConnectorStatus,
    ConnectorCategory,
    ALLOWED_CAPABILITIES,
)
from era.acquisition.connector_models import ConnectorRecord, ResourcePolicy, RetryPolicy, utc_now
from era.acquisition import connector_errors as errors
from era.shared.persistence import PersistenceError
class SourceReliabilityRegistry:
    """
    C4: this is the reference implementation for wiring persistence into
    an engine. Passing `store=` (an era.shared.persistence.SqliteStore)
    makes connector state and audit events survive process exit. Passing
    nothing keeps the original in-memory-only behavior, unchanged, so
    every existing caller and verify script keeps working exactly as
    before.

    Persistence error handling: every mutating method below keeps the
    connector it's about to persist off to one side, applies it to
    self.connectors, and if the durable write then fails, rolls the
    in-memory dict back to what it was and returns
    errors.PERSISTENCE_WRITE_FAILED instead of PASS. This keeps memory
    and disk from silently disagreeing -- a caller either gets a fully
    successful write (both memory and disk agree) or a clean failure
    (memory is exactly what it was before the call), never a partial one.
    """
    TABLE = "acquisition_connectors"
    def __init__(self, store=None):
        self.connectors = {}
        self.store = store
        self.audit = AcquisitionAuditPublisher(
            sink=store.event_sink("era.acquisition.source_reliability_registry") if store else None
        )
        if self.store:
            self._load_from_store()
    def _load_from_store(self):
        for data in self.store.list_records(self.TABLE):
            connector = self._from_dict(data)
            self.connectors[connector.connector_id] = connector
    def _persist(self, connector, conn=None) -> bool:
        if not self.store:
            return True
        try:
            self.store.save_record(self.TABLE, connector.connector_id, self._to_dict(connector), conn=conn)
            return True
        except PersistenceError:
            return False
    @staticmethod
    def _to_dict(connector: ConnectorRecord) -> dict:
        data = asdict(connector)
        data["category"] = connector.category.value
        data["legal_classification"] = connector.legal_classification.value
        data["status"] = connector.status.value
        return data
    @staticmethod
    def _from_dict(data: dict) -> ConnectorRecord:
        data = dict(data)
        data["category"] = ConnectorCategory(data["category"])
        data["legal_classification"] = LegalClassification(data["legal_classification"])
        data["status"] = ConnectorStatus(data["status"])
        data["resource_policy"] = ResourcePolicy(**data["resource_policy"])
        data["retry_policy"] = RetryPolicy(**data["retry_policy"])
        return ConnectorRecord(**data)
    def register_connector(self, connector):
        if not connector.connector_id:
            self.audit.publish("CONNECTOR_FAILED", {"reason": errors.CONNECTOR_REQUIRED})
            return errors.CONNECTOR_REQUIRED, None
        if connector.connector_id in self.connectors:
            self.audit.publish("CONNECTOR_FAILED", {"reason": errors.DUPLICATE_CONNECTOR})
            return errors.DUPLICATE_CONNECTOR, None
        if not isinstance(connector.legal_classification, LegalClassification):
            self.audit.publish("CONNECTOR_FAILED", {"reason": errors.LEGAL_CLASSIFICATION_REQUIRED})
            return errors.LEGAL_CLASSIFICATION_REQUIRED, None
        if not isinstance(connector.category, ConnectorCategory):
            self.audit.publish("CONNECTOR_FAILED", {"reason": "INVALID_CATEGORY"})
            return "INVALID_CATEGORY", None
        if not connector.resource_policy:
            self.audit.publish("CONNECTOR_FAILED", {"reason": errors.RESOURCE_POLICY_REQUIRED})
            return errors.RESOURCE_POLICY_REQUIRED, None
        if connector.resource_policy.rate_limit_per_day <= 0 or connector.resource_policy.max_requests <= 0:
            self.audit.publish("CONNECTOR_FAILED", {"reason": errors.RESOURCE_POLICY_REQUIRED})
            return errors.RESOURCE_POLICY_REQUIRED, None
        if connector.resource_policy.refresh_schedule_hours <= 0:
            self.audit.publish("CONNECTOR_FAILED", {"reason": errors.REFRESH_POLICY_REQUIRED})
            return errors.REFRESH_POLICY_REQUIRED, None
        for capability in connector.capabilities:
            if str(capability).upper() not in ALLOWED_CAPABILITIES:
                self.audit.publish("CONNECTOR_FAILED", {
                    "reason": errors.UNKNOWN_CAPABILITY,
                    "capability": capability,
                })
                return errors.UNKNOWN_CAPABILITY, None
        self.connectors[connector.connector_id] = connector
        if not self._persist(connector):
            del self.connectors[connector.connector_id]
            self.audit.publish("CONNECTOR_FAILED", {
                "reason": errors.PERSISTENCE_WRITE_FAILED,
                "connector_id": connector.connector_id,
            })
            return errors.PERSISTENCE_WRITE_FAILED, None
        self.audit.publish("CONNECTOR_REGISTERED", {
            "connector_id": connector.connector_id,
            "provider_name": connector.provider_name,
            "legal_classification": connector.legal_classification.value,
            "status": connector.status.value,
            "created_at": connector.created_at,
        })
        return errors.PASS, connector
    def enable_connector(self, connector_id: str):
        connector = self.connectors.get(connector_id)
        if not connector:
            self.audit.publish("CONNECTOR_FAILED", {"reason": errors.CONNECTOR_REQUIRED})
            return errors.CONNECTOR_REQUIRED
        updated = replace(connector, status=ConnectorStatus.ACTIVE)
        self.connectors[connector_id] = updated
        if not self._persist(updated):
            self.connectors[connector_id] = connector
            self.audit.publish("CONNECTOR_FAILED", {
                "reason": errors.PERSISTENCE_WRITE_FAILED,
                "connector_id": connector_id,
            })
            return errors.PERSISTENCE_WRITE_FAILED
        self.audit.publish("CONNECTOR_ENABLED", {"connector_id": connector_id})
        return errors.PASS
    def disable_connector(self, connector_id: str):
        connector = self.connectors.get(connector_id)
        if not connector:
            self.audit.publish("CONNECTOR_FAILED", {"reason": errors.CONNECTOR_REQUIRED})
            return errors.CONNECTOR_REQUIRED
        updated = replace(connector, status=ConnectorStatus.DISABLED)
        self.connectors[connector_id] = updated
        if not self._persist(updated):
            self.connectors[connector_id] = connector
            self.audit.publish("CONNECTOR_FAILED", {
                "reason": errors.PERSISTENCE_WRITE_FAILED,
                "connector_id": connector_id,
            })
            return errors.PERSISTENCE_WRITE_FAILED
        self.audit.publish("CONNECTOR_DISABLED", {"connector_id": connector_id})
        return errors.PASS
    def record_success(self, connector_id: str, response_time_ms: int, conn=None):
        connector = self.connectors.get(connector_id)
        if not connector:
            self.audit.publish("CONNECTOR_FAILED", {"reason": errors.CONNECTOR_REQUIRED})
            return errors.CONNECTOR_REQUIRED
        success_count = connector.success_count + 1
        failure_count = connector.failure_count
        total = success_count + failure_count
        success_rate = success_count / total if total else None
        updated = replace(
            connector,
            last_success=utc_now(),
            consecutive_failures=0,
            average_response_time_ms=response_time_ms,
            success_count=success_count,
            success_rate=success_rate,
        )
        self.connectors[connector_id] = updated
        if not self._persist(updated, conn=conn):
            self.connectors[connector_id] = connector
            self.audit.publish("CONNECTOR_FAILED", {
                "reason": errors.PERSISTENCE_WRITE_FAILED,
                "connector_id": connector_id,
            })
            return errors.PERSISTENCE_WRITE_FAILED
        self.audit.publish("CONNECTOR_COMPLETED", {
            "connector_id": connector_id,
            "response_time_ms": response_time_ms,
            "success_rate": success_rate,
        })
        return errors.PASS
    def record_failure(self, connector_id: str, conn=None):
        connector = self.connectors.get(connector_id)
        if not connector:
            self.audit.publish("CONNECTOR_FAILED", {"reason": errors.CONNECTOR_REQUIRED})
            return errors.CONNECTOR_REQUIRED
        success_count = connector.success_count
        failure_count = connector.failure_count + 1
        total = success_count + failure_count
        success_rate = success_count / total if total else None
        updated = replace(
            connector,
            last_failure=utc_now(),
            consecutive_failures=connector.consecutive_failures + 1,
            failure_count=failure_count,
            success_rate=success_rate,
        )
        self.connectors[connector_id] = updated
        if not self._persist(updated, conn=conn):
            self.connectors[connector_id] = connector
            self.audit.publish("CONNECTOR_FAILED", {
                "reason": errors.PERSISTENCE_WRITE_FAILED,
                "connector_id": connector_id,
            })
            return errors.PERSISTENCE_WRITE_FAILED
        self.audit.publish("CONNECTOR_FAILED", {
            "connector_id": connector_id,
            "consecutive_failures": updated.consecutive_failures,
            "success_rate": success_rate,
        })
        return errors.PASS
    def attempt_evidence_modification(self):
        self.audit.publish("CONNECTOR_FAILED", {"reason": errors.READ_ONLY_CONNECTOR})
        return False, errors.READ_ONLY_CONNECTOR
    def attempt_confidence_assignment(self):
        self.audit.publish("CONNECTOR_FAILED", {"reason": errors.CONFIDENCE_AUTHORITY_VIOLATION})
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
    def get_connector(self, connector_id: str):
        return self.connectors.get(connector_id)
    def list_connectors(self):
        """Deterministic read-only provider enumeration seed (PER-001)."""
        return tuple(self.connectors[key] for key in sorted(self.connectors))
