from era.acquisition.profiles.collin_profile import map_collin_row


def test_collin_mapping_enforces_source_rules():
    row = {
        "prop_id": 101,
        "geo_id": "R-TEST",
        "file_as_name": "OWNER",
        "addr_line1": "PO BOX 10",
        "addr_line2": None,
        "addr_line3": None,
        "addr_city": "DALLAS",
        "addr_state": "TX",
        "addr_zip": "75000",
        "situs_display": "100 MAIN ST, PLANO, TX 75001",
        "situs_city": "PLANO",
        "situs_state": "TX",
        "situs_zip": "75001",
        "land_sqft": 1,
        "land_total_sqft": 2000,
        "property_status": "Preliminary",
        "curr_market": None,
        "cert_market": 300000,
        "state_cd": "A1",
        "property_use_cd": "UNKNOWN",
        "land_type_cd": None,
    }
    codes = {"State Category Codes": {"A1": "Residential Single-Family"}, "Property Use Codes": {}, "Land Type Codes": {}}

    evidence, warnings = map_collin_row(row, codes)

    assert evidence["source_record_id"] == "101"
    assert evidence["parcel_id"] == "R-TEST"
    assert evidence["property_address"] != evidence["owner_mailing_address"]
    assert "land_sqft" not in evidence
    assert evidence["land_area_sqft"] == "2000"
    assert "current_market_value" not in evidence
    assert evidence["certified_market_value"] == "300000"
    assert evidence["state_description"] == "Residential Single-Family"
    assert evidence["property_use_code"] == "UNKNOWN"
    assert "property_use_description" not in evidence
    assert warnings == ("UNKNOWN_CODE:property_use_cd:UNKNOWN",)


def test_current_values_are_ignored_outside_preliminary_status():
    evidence, warnings = map_collin_row(
        {"property_status": "Certified", "curr_market": 999, "cert_market": 888},
        {"State Category Codes": {}, "Property Use Codes": {}, "Land Type Codes": {}},
    )
    assert "current_market_value" not in evidence
    assert evidence["certified_market_value"] == "888"
    assert warnings == ()
