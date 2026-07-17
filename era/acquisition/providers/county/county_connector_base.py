from abc import ABC, abstractmethod
from era.acquisition.providers.county.county_framework_audit import CountyFrameworkAudit
from era.acquisition.providers.county.county_framework_models import CountyRawEvidence
from era.acquisition.providers.county import county_framework_errors as errors
class CountyConnectorBase(ABC):
    """
    Base contract for all county public-record connectors.
    This class defines lifecycle and guard behavior.
    County-specific connectors implement only provider-specific lookup details.
    """
    CONNECTOR_ID = "BASE_COUNTY_CONNECTOR"
    PROVIDER_NAME = "County Provider"
    SOURCE_NAME = "County Public Records"
    LEGAL_BASIS = "PUBLIC_RECORD"
    SUPPORTED_COUNTY = ""
    def __init__(self, audit=None):
        self.audit = audit or CountyFrameworkAudit()
    def run(self, request):
        if request is None or not request.property_id or not request.address:
            self.audit.publish("COUNTY_CONNECTOR_BLOCKED", {
                "reason": errors.COUNTY_INPUT_REQUIRED,
            })
            return errors.COUNTY_INPUT_REQUIRED, []
        if self.SUPPORTED_COUNTY and request.county.lower() != self.SUPPORTED_COUNTY.lower():
            self.audit.publish("COUNTY_CONNECTOR_BLOCKED", {
                "reason": errors.COUNTY_NOT_SUPPORTED,
                "requested_county": request.county,
                "supported_county": self.SUPPORTED_COUNTY,
            })
            return errors.COUNTY_NOT_SUPPORTED, []
        if not self.health_check():
            self.audit.publish("COUNTY_CONNECTOR_BLOCKED", {
                "reason": errors.CONNECTOR_HEALTH_FAILED,
            })
            return errors.CONNECTOR_HEALTH_FAILED, []
        search_status, provider_key = self.search_property(request)
        if search_status != errors.PASS:
            self.audit.publish("COUNTY_CONNECTOR_BLOCKED", {
                "reason": errors.SEARCH_FAILED,
            })
            return errors.SEARCH_FAILED, []
        retrieval_status, data = self.retrieve_public_record(request, provider_key)
        if retrieval_status != errors.PASS:
            self.audit.publish("COUNTY_CONNECTOR_BLOCKED", {
                "reason": errors.RETRIEVAL_FAILED,
            })
            return errors.RETRIEVAL_FAILED, []
        validation_status = self.validate(data)
        if validation_status != errors.PASS:
            self.audit.publish("COUNTY_CONNECTOR_BLOCKED", {
                "reason": errors.VALIDATION_FAILED,
            })
            return errors.VALIDATION_FAILED, []
        evidence = self.publish_raw_evidence(request, data)
        if not evidence:
            self.audit.publish("COUNTY_CONNECTOR_BLOCKED", {
                "reason": errors.RAW_EVIDENCE_EMPTY,
            })
            return errors.RAW_EVIDENCE_EMPTY, []
        self.audit.publish("COUNTY_CONNECTOR_COMPLETED", {
            "connector_id": self.CONNECTOR_ID,
            "property_id": request.property_id,
            "county": request.county,
            "evidence_count": len(evidence),
        })
        return errors.PASS, evidence
    def publish_raw_evidence(self, request, data: dict):
        evidence = []
        for index, key in enumerate(sorted(data.keys()), start=1):
            value = data[key]
            if value is None or value == "":
                continue
            evidence.append(
                CountyRawEvidence(
                    evidence_id=f"RAW-{self.CONNECTOR_ID}-{index:03d}",
                    property_id=request.property_id,
                    connector_id=self.CONNECTOR_ID,
                    county=request.county,
                    provider_name=self.PROVIDER_NAME,
                    source_name=self.SOURCE_NAME,
                    legal_basis=self.LEGAL_BASIS,
                    field_name=key,
                    raw_value=str(value),
                )
            )
        return evidence
    def attempt_write(self):
        self.audit.publish("COUNTY_CONNECTOR_BLOCKED", {
            "reason": errors.READ_ONLY_COUNTY_CONNECTOR,
        })
        return False, errors.READ_ONLY_COUNTY_CONNECTOR
    def assign_confidence(self):
        self.audit.publish("COUNTY_CONNECTOR_BLOCKED", {
            "reason": errors.CONFIDENCE_AUTHORITY_VIOLATION,
        })
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
    @abstractmethod
    def health_check(self): ...
    @abstractmethod
    def search_property(self, request): ...
    @abstractmethod
    def retrieve_public_record(self, request, provider_key): ...
    @abstractmethod
    def validate(self, data): ...
