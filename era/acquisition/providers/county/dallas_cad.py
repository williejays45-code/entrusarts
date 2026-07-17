from era.acquisition.providers.county.county_connector_base import CountyConnectorBase
from era.acquisition.providers.county import county_framework_errors as errors
class DallasCADConnector(CountyConnectorBase):
    CONNECTOR_ID = "COUNTY_DALLAS_CAD"
    PROVIDER_NAME = "Dallas Central Appraisal District"
    SOURCE_NAME = "Dallas CAD Public Records"
    LEGAL_BASIS = "PUBLIC_RECORD"
    SUPPORTED_COUNTY = "Dallas"
    def health_check(self):
        return True
    def search_property(self, request):
        provider_key = request.parcel_apn or request.address
        if not provider_key:
            return errors.SEARCH_FAILED, None
        return errors.PASS, provider_key
    def retrieve_public_record(self, request, provider_key):
        # Stubbed provider response.
        # Live retrieval must use authorized/public access paths only.
        data = {
            "property_address": request.address.title(),
            "city": request.city.title(),
            "county": request.county,
            "state": request.state,
            "property_type": "CONDOMINIUM",
        }
        return errors.PASS, data
    def validate(self, data):
        required = ["property_address", "city", "county", "state"]
        if any(not data.get(field) for field in required):
            return errors.VALIDATION_FAILED
        return errors.PASS
