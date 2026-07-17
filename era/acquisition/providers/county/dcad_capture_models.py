from dataclasses import dataclass, field
from datetime import datetime, timezone
def utc_now():
    return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class DCADPublicRecord:
    property_id: str
    account_number: str
    address: str
    owner: str
    legal_description: str
    property_class: str
    year_built: str
    living_area: str
    appraised_value: str
    land_value: str
    improvement_value: str
    exemptions: str
    tax_year: str
    source_name: str = "Dallas Central Appraisal District"
    legal_basis: str = "PUBLIC_RECORD"
    retrieved_at: str = field(default_factory=utc_now)
