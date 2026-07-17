from __future__ import annotations

import os
import csv
from pathlib import Path

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SYNTHETIC_MARKER = "ERA_SYNTHETIC_TEST_DATA_V1"
SYNTHETIC_APPR_FILENAME = "ACCOUNT_APPRL_YEAR_SYNTHETIC.csv"
SYNTHETIC_INFO_FILENAME = "ACCOUNT_INFO_SYNTHETIC.csv"
REAL_DATA_FILENAMES = frozenset({
    "ACCOUNT_APPRL_YEAR_FIXTURE.CSV",
    "ACCOUNT_INFO_FIXTURE.CSV",
})

SYNTHETIC_ACCOUNT_BASELINE = "0000-SYNTH-BASE-01"
SYNTHETIC_ACCOUNT_UNIT = "SYNTH-UNIT-000002"
SYNTHETIC_ACCOUNT_HALF = "SYNTH-HALF-000003"
SYNTHETIC_BASE_OWNER = "SYNTHETIC PERSON ALPHA"
SYNTHETIC_BASE_ADDRESS = "100 FICTIONAL WAY"
SYNTHETIC_UNIT_ADDRESS = "200 IMAGINARY AVE BLDG TEST-B UNIT TEST-42"
SYNTHETIC_HALF_ADDRESS_PREFIX = "300Z "
SYNTHETIC_CITY = "FICTIONVILLE"
SYNTHETIC_BASE_TOTAL = "123456.78"
SYNTHETIC_BASE_LEGAL = (
    "SYNTHETIC ESTATES | BLOCK TEST LOT 1 | FICTIONAL WAY | "
    "TEST DEED 0001 | SYNTHETIC PARCEL DESCRIPTION"
)

REQUIRED_SYNTHETIC_APPR_COLUMNS = frozenset({
    "ACCOUNT_NUM", "APPRAISAL_YR", "TOT_VAL", "LAND_VAL", "IMPR_VAL",
    "CITY_JURIS_DESC", "COUNTY_JURIS_DESC", "GIS_PARCEL_ID", "SYNTHETIC_MARKER",
})
REQUIRED_SYNTHETIC_INFO_COLUMNS = frozenset({
    "ACCOUNT_NUM", "APPRAISAL_YR", "OWNER_NAME1", "OWNER_NAME2",
    "STREET_NUM", "STREET_HALF_NUM", "FULL_STREET_NAME", "BLDG_ID", "UNIT_ID",
    "PROPERTY_CITY", "PROPERTY_ZIPCODE", "LEGAL1", "LEGAL2", "LEGAL3", "LEGAL4",
    "LEGAL5", "GIS_PARCEL_ID", "PHONE_NUM", "SYNTHETIC_MARKER",
})


def synthetic_fixture_paths() -> tuple[Path, Path]:
    return _FIXTURE_DIR / SYNTHETIC_APPR_FILENAME, _FIXTURE_DIR / SYNTHETIC_INFO_FILENAME


def validate_synthetic_fixtures() -> dict[str, bool]:
    appr_path, info_path = synthetic_fixture_paths()
    paths = (appr_path, info_path)
    checks = {
        "synthetic_fixtures_exist": all(path.is_file() for path in paths),
        "synthetic_filenames_explicit": all("SYNTHETIC" in path.name.upper() for path in paths),
        "fallback_is_fixture_local": all(path.parent == _FIXTURE_DIR for path in paths),
        "real_filenames_never_selected": REAL_DATA_FILENAMES.isdisjoint(path.name for path in paths),
    }
    if not checks["synthetic_fixtures_exist"]:
        return checks

    with appr_path.open(newline="", encoding="utf-8") as stream:
        appr_reader = csv.DictReader(stream)
        appr_rows = list(appr_reader)
        appr_columns = frozenset(appr_reader.fieldnames or ())
    with info_path.open(newline="", encoding="utf-8") as stream:
        info_reader = csv.DictReader(stream)
        info_rows = list(info_reader)
        info_columns = frozenset(info_reader.fieldnames or ())

    checks.update({
        "appraisal_required_columns_present": REQUIRED_SYNTHETIC_APPR_COLUMNS <= appr_columns,
        "info_required_columns_present": REQUIRED_SYNTHETIC_INFO_COLUMNS <= info_columns,
        "synthetic_rows_present": bool(appr_rows) and bool(info_rows),
        "every_row_marked_synthetic": all(
            row.get("SYNTHETIC_MARKER") == SYNTHETIC_MARKER
            for row in appr_rows + info_rows
        ),
        "fixture_accounts_are_explicitly_synthetic": all(
            "SYNTH" in row.get("ACCOUNT_NUM", "").upper()
            for row in appr_rows + info_rows
        ),
    })
    return checks

def resolve_dcad_test_paths() -> tuple[str, str, bool]:
    """Return appraisal path, info path, and whether they are full production files.

    Full data can be supplied portably with ERA_DCAD_APPR_PATH and
    ERA_DCAD_INFO_PATH. Routine verification falls back only to bundled,
    deliberately fabricated synthetic fixtures.
    """
    appr = os.environ.get("ERA_DCAD_APPR_PATH")
    info = os.environ.get("ERA_DCAD_INFO_PATH")
    if appr and info and Path(appr).is_file() and Path(info).is_file():
        return appr, info, True
    checks = validate_synthetic_fixtures()
    if not checks or not all(checks.values()):
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise RuntimeError(f"SYNTHETIC_FIXTURE_VALIDATION_FAILED: {failed}")
    appr_path, info_path = synthetic_fixture_paths()
    return str(appr_path), str(info_path), False
