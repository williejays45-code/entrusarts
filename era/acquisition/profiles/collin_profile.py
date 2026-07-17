from dataclasses import dataclass
from enum import Enum


class AcquisitionTechnology(str, Enum):
    BULK_MDB = "BULK_MDB"


@dataclass(frozen=True)
class SourceProfile:
    profile_id: str
    jurisdiction_code: str
    technology: AcquisitionTechnology
    provider_id: str
    source_name: str
    mapping_version: str
    enabled: bool


COLLIN_PROFILE = SourceProfile(
    profile_id="CCS-001",
    jurisdiction_code="TX-COLLIN",
    technology=AcquisitionTechnology.BULK_MDB,
    provider_id="COLLIN_BULK_MDB",
    source_name="Collin CAD AD_Public",
    mapping_version="AD_PUBLIC-2013.1",
    enabled=True,
)


CODE_SHEETS = {
    "state_cd": "State Category Codes",
    "property_use_cd": "Property Use Codes",
    "land_type_cd": "Land Type Codes",
}


# Deliberately excludes land_sqft. AD_Public_FileLayout.pdf says DO NOT USE.
SOURCE_COLUMNS = (
    "prop_id", "geo_id", "file_as_name",
    "addr_line1", "addr_line2", "addr_line3", "addr_city", "addr_state", "addr_zip",
    "situs_display", "situs_city", "situs_state", "situs_zip",
    "legal_desc", "legal_acreage", "eff_size_acres", "land_total_sqft", "living_area",
    "state_cd", "property_use_cd", "prop_type_cd", "land_type_cd", "commercial_flag",
    "eff_yr_blt", "yr_blt", "beds", "baths", "stories", "units", "pool",
    "property_status",
    "curr_val_yr", "curr_imprv_hstd_val", "curr_imprv_non_hstd_val",
    "curr_land_hstd_val", "curr_land_non_hstd_val", "curr_ag_use_val",
    "curr_ag_market", "curr_market", "curr_ag_loss", "curr_appraised_val",
    "curr_ten_percent_cap", "curr_assessed_val",
    "cert_val_yr", "cert_imprv_hstd_val", "cert_imprv_non_hstd_val",
    "cert_land_hstd_val", "cert_land_non_hstd_val", "cert_ag_use_val",
    "cert_ag_market", "cert_market", "cert_ag_loss", "cert_appraised_val",
    "cert_ten_percent_cap", "cert_assessed_val",
)


DIRECT_FIELD_MAP = {
    "prop_id": "source_record_id",
    "geo_id": "parcel_id",
    "file_as_name": "owner_name",
    "situs_display": "property_address",
    "situs_city": "city",
    "situs_state": "state",
    "situs_zip": "zip_code",
    "legal_desc": "legal_description",
    "legal_acreage": "legal_acreage",
    "eff_size_acres": "effective_size_acres",
    "land_total_sqft": "land_area_sqft",
    "living_area": "living_area",
    "prop_type_cd": "property_type_code",
    "commercial_flag": "commercial_flag",
    "eff_yr_blt": "effective_year_built",
    "yr_blt": "year_built",
    "beds": "bedrooms",
    "baths": "bathrooms",
    "stories": "stories",
    "units": "units",
    "pool": "pool",
    "property_status": "property_status",
    "cert_val_yr": "certified_value_year",
    "cert_imprv_hstd_val": "certified_improvement_homesite_value",
    "cert_imprv_non_hstd_val": "certified_improvement_non_homesite_value",
    "cert_land_hstd_val": "certified_land_homesite_value",
    "cert_land_non_hstd_val": "certified_land_non_homesite_value",
    "cert_ag_use_val": "certified_ag_use_value",
    "cert_ag_market": "certified_ag_market_value",
    "cert_market": "certified_market_value",
    "cert_ag_loss": "certified_ag_loss_value",
    "cert_appraised_val": "certified_appraised_value",
    "cert_ten_percent_cap": "certified_ten_percent_cap",
    "cert_assessed_val": "certified_assessed_value",
}


CURRENT_FIELD_MAP = {
    "curr_val_yr": "current_value_year",
    "curr_imprv_hstd_val": "current_improvement_homesite_value",
    "curr_imprv_non_hstd_val": "current_improvement_non_homesite_value",
    "curr_land_hstd_val": "current_land_homesite_value",
    "curr_land_non_hstd_val": "current_land_non_homesite_value",
    "curr_ag_use_val": "current_ag_use_value",
    "curr_ag_market": "current_ag_market_value",
    "curr_market": "current_market_value",
    "curr_ag_loss": "current_ag_loss_value",
    "curr_appraised_val": "current_appraised_value",
    "curr_ten_percent_cap": "current_ten_percent_cap",
    "curr_assessed_val": "current_assessed_value",
}


def map_collin_row(row, code_lists):
    evidence = {}
    warnings = []

    for source, target in DIRECT_FIELD_MAP.items():
        value = row.get(source)
        if value not in (None, ""):
            evidence[target] = str(value).strip()

    # The official layout defines commercial_flag as t/f, while the
    # canonical BOOLEAN contract accepts true/false (and y/n).
    commercial = str(row.get("commercial_flag") or "").strip().lower()
    if commercial in {"t", "f"}:
        evidence["commercial_flag"] = "true" if commercial == "t" else "false"

    mailing_parts = [row.get(name) for name in ("addr_line1", "addr_line2", "addr_line3")]
    mailing_lines = [str(value).strip() for value in mailing_parts if value not in (None, "")]
    if mailing_lines:
        evidence["owner_mailing_address"] = ", ".join(mailing_lines)
    for source, target in (
        ("addr_city", "owner_mailing_city"),
        ("addr_state", "owner_mailing_state"),
        ("addr_zip", "owner_mailing_zip_code"),
    ):
        value = row.get(source)
        if value not in (None, ""):
            evidence[target] = str(value).strip()

    status = str(row.get("property_status") or "").strip()
    if status.lower() == "preliminary":
        for source, target in CURRENT_FIELD_MAP.items():
            value = row.get(source)
            if value not in (None, ""):
                evidence[target] = str(value).strip()

    for source, sheet in CODE_SHEETS.items():
        value = row.get(source)
        if value in (None, ""):
            continue
        code = str(value).strip()
        evidence[source.replace("_cd", "_code")] = code
        resolved = code_lists.get(sheet, {}).get(code.upper())
        if resolved:
            evidence[source.replace("_cd", "_description")] = resolved
        else:
            warnings.append(f"UNKNOWN_CODE:{source}:{code}")

    return evidence, tuple(warnings)
