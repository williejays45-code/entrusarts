from era.acquisition.connector_enums import ConnectorStatus
from era.acquisition.providers.county.county_models import RawCountyEvidence
from era.acquisition.providers.county.county_audit import CountyConnectorAudit
from era.acquisition.providers.county import county_errors as errors
class TarrantCountyAssessorConnector:
    """
    EAE-001.3 governed county connector scaffold.
    This connector does not scrape websites.
    It represents the approved connector contract for public-record retrieval.
    Live retrieval will be added only through authorized/public access paths.
    """
    CONNECTOR_ID = "COUNTY_TARRANT_ASSESSOR"
    PROVIDER_NAME = "Tarrant County Assessor"
    SOURCE_NAME = "County Public Records"
    LEGAL_BASIS = "PUBLIC_RECORD"
    def __init__(self, source_registry, audit=None):
        self.source_registry = source_registry
        self.audit = audit or CountyConnectorAudit()
    def retrieve(self, request):
        if request is None or not request.property_id:
            self.audit.publish("COUNTY_CONNECTOR_BLOCKED", {
                "reason": errors.CONNECTOR_INPUT_REQUIRED,
            })
            return errors.CONNECTOR_INPUT_REQUIRED, []
        connector = self.source_registry.get_connector(self.CONNECTOR_ID)
        if connector is None:
            self.audit.publish("COUNTY_CONNECTOR_BLOCKED", {
                "reason": errors.CONNECTOR_INPUT_REQUIRED,
            })
            return errors.CONNECTOR_INPUT_REQUIRED, []
        if connector.status != ConnectorStatus.ACTIVE:
            self.audit.publish("COUNTY_CONNECTOR_BLOCKED", {
                "reason": errors.CONNECTOR_NOT_ACTIVE,
                "connector_id": self.CONNECTOR_ID,
            })
            return errors.CONNECTOR_NOT_ACTIVE, []
        if connector.legal_classification.value != self.LEGAL_BASIS:
            self.audit.publish("COUNTY_CONNECTOR_BLOCKED", {
                "reason": errors.LEGAL_SOURCE_REQUIRED,
                "connector_id": self.CONNECTOR_ID,
            })
            return errors.LEGAL_SOURCE_REQUIRED, []
        raw = self._retrieve_public_record_stub(request)
        if not raw:
            self.audit.publish("COUNTY_CONNECTOR_BLOCKED", {
                "reason": errors.RAW_EVIDENCE_EMPTY,
                "property_id": request.property_id,
            })
            self.source_registry.record_failure(self.CONNECTOR_ID)
            return errors.RAW_EVIDENCE_EMPTY, []
        self.source_registry.record_success(self.CONNECTOR_ID, 120)
        self.audit.publish("COUNTY_CONNECTOR_COMPLETED", {
            "connector_id": self.CONNECTOR_ID,
            "property_id": request.property_id,
            "evidence_count": len(raw),
        })
        return errors.PASS, raw
    def _retrieve_public_record_stub(self, request):
        normalized_address = " ".join(str(request.address).split()).title()
        return [
            RawCountyEvidence(
                evidence_id="RAW-TARRANT-001",
                property_id=request.property_id,
                connector_id=self.CONNECTOR_ID,
                provider_name=self.PROVIDER_NAME,
                source_name=self.SOURCE_NAME,
                legal_basis=self.LEGAL_BASIS,
                field_name="property_address",
                raw_value=normalized_address,
            ),
            RawCountyEvidence(
                evidence_id="RAW-TARRANT-002",
                property_id=request.property_id,
                connector_id=self.CONNECTOR_ID,
                provider_name=self.PROVIDER_NAME,
                source_name=self.SOURCE_NAME,
                legal_basis=self.LEGAL_BASIS,
                field_name="county",
                raw_value=request.county,
            ),
            RawCountyEvidence(
                evidence_id="RAW-TARRANT-003",
                property_id=request.property_id,
                connector_id=self.CONNECTOR_ID,
                provider_name=self.PROVIDER_NAME,
                source_name=self.SOURCE_NAME,
                legal_basis=self.LEGAL_BASIS,
                field_name="state",
                raw_value=request.state,
            ),
        ]
    def attempt_write(self):
        self.audit.publish("COUNTY_CONNECTOR_BLOCKED", {
            "reason": errors.READ_ONLY_CONNECTOR,
        })
        return False, errors.READ_ONLY_CONNECTOR
    def assign_confidence(self):
        self.audit.publish("COUNTY_CONNECTOR_BLOCKED", {
            "reason": errors.CONFIDENCE_AUTHORITY_VIOLATION,
        })
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
