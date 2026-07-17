"""
LIVE-ADAPTER-001B + DCAD-JOIN-001: DCAD Bulk Data Adapter.

Source: Dallas Central Appraisal District, DCAD Data Products,
"2025 Certified Data Files with Supplemental Changes (Comma Delimited)".
Access mode: official published downloadable data product (a ZIP
containing certified CSV tables) -- not the public property-search UI,
never scraped, never automated as a search.

Schema provenance -- both tables below were read directly from the
actual uploaded certified files, not inferred or transcribed from a
description:

- Account_Apprl_Year: CONFIRMED. 47 columns, 858,533 real rows, every
  ACCOUNT_NUM unique, APPRAISAL_YR uniformly 2025.
- Account_Info: CONFIRMED. 34 columns, 858,533 real rows, every
  (ACCOUNT_NUM, APPRAISAL_YR) pair unique. Cross-checked against
  Account_Apprl_Year for the same real account (00000416479000000) as
  a genuine two-table consistency check, not two independent claims
  taken on faith.
- DCAD_Data_Dictionary.rtf: table-purpose-level only, confirmed via two
  independent extraction methods. Never a source for any column name.
- Every other table (Land, Res_Detail, Res_Addl, Com_Detail,
  Taxable_Object, the exemption tables, Account_TIF): not used by this
  adapter. Account_TIF was uploaded alongside Account_Info but is
  outside this task's stated scope -- not referenced here.

Real-data findings that shaped this join (checked at full scale
across all 858,533 rows, not sampled):
- OWNER_NAME2 is populated in ZERO real rows. The "OWNER_NAME1 +
  OWNER_NAME2" concatenation path exists and is tested, but only
  against a synthetic row -- flagged as such in the verify suite, since
  no real example currently exists to confirm against.
- STREET_NUM and FULL_STREET_NAME are populated in EVERY real row --
  a genuinely blank situs address does not occur in this dataset. The
  "unmatched central record degrades honestly" and "blank situs" paths
  are real code, exercised by synthetic rows for the same reason.
- A meaningful fraction of real LEGAL1-5 text collided with
  CanonicalEvidenceModel's TEXT leakage regex (e.g. real LEGAL3 text
  "BLDG B UNIT 206  5% OF CE" matches \\d+%). Measured at ~3.8% of
  individual legal-line cells in a 50,000-row sample. FIXED in
  ECM-OFFICIAL-TEXT-001: legal_description is now submitted as
  OFFICIAL_TEXT (era.pipeline.FIELD_VALUE_TYPE), which allows ordinary
  decimals/percentages in authoritative source text while still
  blocking genuine confidence-vocabulary injection
  (confidence=/score=/probability=/reliability=). See
  canonical_engine.py's OFFICIAL_TEXT_LEAK_PATTERNS.

Address construction (per FORGE's rule): STREET_NUM + STREET_HALF_NUM
(directly appended, e.g. "44" + "A" -> "44A", when present) + a space +
FULL_STREET_NAME (stripped -- real data has trailing whitespace on this
column) + " BLDG {BLDG_ID}" when present + " UNIT {UNIT_ID}" when
present. The exact separator/label choice is not otherwise specified;
this is a documented, reasonable construction, not asserted as DCAD's
own canonical format.

Never substitutes OWNER_ADDRESS_LINE* for property_address when situs
fields are missing -- per FORGE's explicit rule. If STREET_NUM or
FULL_STREET_NAME is missing, property_address is simply not produced,
the same honest-gap posture as Phase 1.
"""

import csv
import io
import zipfile

from era.live_adapters import dcad_bulk_errors as errors
from era.live_adapters.dcad_bulk_data_models import DCADAccountMapping
from era.network.network_client import NetworkClient
from era.network.http_transport import UrllibHttpTransport
from era.network import network_errors as network_errors
from era.providers.provider_models import ProviderEvidence
from era.providers import provider_errors as provider_errors
from era.shared.audit import BaseAuditPublisher
from era.live_adapters.dcad_index_store import DCADIndexStore, compute_fingerprint, DCADIndexBuildError
from era.auth.auth_enums import AuthPermission

# Real columns, confirmed directly from the uploaded certified CSV
# headers (both tables). ERA field name -> DCAD column name.
ACCOUNT_APPRL_YEAR_FIELD_MAP = {
    "city": "CITY_JURIS_DESC",           # Phase 1 fallback when Account_Info isn't joined -- see retrieve()
    "county": "COUNTY_JURIS_DESC",
    "total_appraised_value": "TOT_VAL",
    "land_value": "LAND_VAL",
    "improvement_value": "IMPR_VAL",
    "parcel_id": "GIS_PARCEL_ID",
}
STATE_CONSTANT = "TX"

REQUIRED_APPRL_YEAR_COLUMNS = {"ACCOUNT_NUM", "APPRAISAL_YR"}
REQUIRED_ACCOUNT_INFO_COLUMNS = {"ACCOUNT_NUM", "APPRAISAL_YR"}


def _clean(value):
    if value is None:
        return ""
    return str(value).strip()


def _build_property_address(info_row: dict) -> str:
    """Real construction rule, per FORGE:
    STREET_NUM + STREET_HALF_NUM (when present) + FULL_STREET_NAME
    + BLDG_ID (when present) + UNIT_ID (when present).
    Never substitutes an owner mailing address."""
    street_num = _clean(info_row.get("STREET_NUM"))
    if not street_num:
        return ""
    street_name = _clean(info_row.get("FULL_STREET_NAME"))
    if not street_name:
        return ""
    half = _clean(info_row.get("STREET_HALF_NUM"))
    number_part = f"{street_num}{half}" if half else street_num
    parts = [number_part, street_name]
    bldg = _clean(info_row.get("BLDG_ID"))
    if bldg:
        parts.append(f"BLDG {bldg}")
    unit = _clean(info_row.get("UNIT_ID"))
    if unit:
        parts.append(f"UNIT {unit}")
    return " ".join(parts)


def _build_owner_name(info_row: dict) -> str:
    name1 = _clean(info_row.get("OWNER_NAME1"))
    name2 = _clean(info_row.get("OWNER_NAME2"))
    if name1 and name2:
        return f"{name1}; {name2}"
    return name1 or name2


def _build_legal_description(info_row: dict) -> str:
    """LEGAL1-5 combined without blanks -- only non-empty lines are
    joined, in order, so a record with fewer than 5 populated lines
    doesn't carry empty separators."""
    lines = [_clean(info_row.get(f"LEGAL{i}")) for i in range(1, 6)]
    return " | ".join(line for line in lines if line)


class DCADBulkDataAdapter:
    CONNECTOR_ID = "DCAD_BULK_DATA_2025"
    PROVIDER_NAME = "DCAD Data Products - 2025 Certified Data Files"
    DEFAULT_TARGET_ENTRY = "ACCOUNT_APPRL_YEAR.CSV"
    # Best-labeled guess, same unconfirmed-ZIP-internal-naming caveat
    # as DEFAULT_TARGET_ENTRY above -- the real archive was never
    # provided, only the extracted CSVs were.
    DEFAULT_ACCOUNT_INFO_ENTRY = "ACCOUNT_INFO.CSV"

    def __init__(self, download_url: str, target_entry_name: str = None,
                 account_info_entry_name: str = None, join_account_info: bool = False,
                 transport=None, audit=None, version: str = "2025-certified",
                 index_db_path: str = "dcad_index.db", index_store=None, auth=None):
        if not download_url:
            raise ValueError(
                "download_url is required -- the real DCAD Data Products "
                "URL has never been confirmed from this environment. See "
                "module docstring."
            )
        self._download_url = download_url
        self._target_entry_name = target_entry_name or self.DEFAULT_TARGET_ENTRY
        self._account_info_entry_name = account_info_entry_name or self.DEFAULT_ACCOUNT_INFO_ENTRY
        # DCAD-JOIN-001 is opt-in: Phase 1 behavior (Account_Apprl_Year
        # only, city from CITY_JURIS_DESC, no address/owner/legal) is
        # completely unchanged unless a caller explicitly asks for the
        # join. Same opt-in discipline as every other extension in this
        # codebase.
        self._join_account_info = join_account_info
        self._transport = transport or UrllibHttpTransport()
        self._version = version
        self.audit = audit or BaseAuditPublisher()
        # DCAD-MAP-AUTH-001: auth is intentionally NOT defaulted to a
        # real AuthEngine -- same fail-closed discipline as
        # ManualRecordAdapter (OP-AUTH-001) and EraApiEngine
        # (AUTH-WIRE-001). Without one wired in,
        # register_account_mapping() refuses every call rather than
        # silently accepting an unauthenticated provider-configuration
        # change. retrieve() is deliberately NOT gated by this at
        # all -- an ordinary property lookup stays read-only and
        # doesn't need elevated mapping authority; only the act of
        # registering/mutating which ACCOUNT_NUM a property_id maps to
        # does.
        self.auth = auth
        self._mappings = {}
        # DCAD-INDEX-001: disk-backed index, not an in-memory dict.
        # Indexing just Account_Apprl_Year alone (858,533 real rows) as
        # a Python dict measured at 2.9 GB RSS and the process was
        # killed attempting to also index Account_Info -- see
        # dcad_index_store.py's module docstring for the full account.
        # index_store can be injected directly (tests use this to point
        # at a temp file); otherwise a DCADIndexStore is built against
        # index_db_path.
        self._index_store = index_store or DCADIndexStore(index_db_path)
        self._duplicate_join_keys = {"appraisal_year": 0, "account_info": 0}
        # AX-ADAPT-001: populated only from actual HTTP response bytes,
        # before ZIP or CSV parsing. Never reconstructed from evidence.
        self._last_raw_source_bytes = None

    def register_account_mapping(self, mapping: DCADAccountMapping, token: str):
        """DCAD-MAP-AUTH-001: requires a valid, non-expired token
        carrying ADMIN or FOUNDER permission. This registers which
        real-world ACCOUNT_NUM a property_id resolves to -- a
        provider-configuration change, not a data read -- so it's held
        to the higher bar the manual adapter's own capture staging
        already established for a different reason (there, a human
        was attesting to facts; here, a caller is redirecting where
        evidence comes from). retrieve() itself is intentionally never
        gated this way -- looking up an already-registered mapping
        stays read-only."""
        if self.auth is None:
            self.audit.publish("DCAD_MAPPING_BLOCKED", {"reason": errors.AUTH_ENGINE_REQUIRED})
            return errors.AUTH_ENGINE_REQUIRED, False

        auth_status, auth_result = self.auth.authenticate(token)
        if auth_status != "PASS":
            self.audit.publish("DCAD_MAPPING_BLOCKED", {"reason": auth_status})
            return auth_status, False

        authz_status = self.auth.authorize(auth_result, AuthPermission.ADMIN)
        has_founder = "FOUNDER" in auth_result.permissions
        if authz_status != "PASS" and not has_founder:
            self.audit.publish("DCAD_MAPPING_BLOCKED", {
                "reason": authz_status, "user_id": auth_result.user_id, "role": auth_result.role,
            })
            return authz_status, False

        if not mapping or not mapping.property_id or not mapping.account_num:
            self.audit.publish("DCAD_MAPPING_BLOCKED", {
                "reason": errors.ACCOUNT_MAPPING_REQUIRED,
                "user_id": auth_result.user_id, "role": auth_result.role,
            })
            return errors.ACCOUNT_MAPPING_REQUIRED, False
        self._mappings[mapping.property_id] = mapping
        self.audit.publish("DCAD_MAPPING_REGISTERED", {
            "property_id": mapping.property_id,
            "account_num": mapping.account_num,
            "appraisal_yr": mapping.appraisal_yr,
            "registered_by": auth_result.user_id,
            "role": auth_result.role,
        })
        return errors.PASS, True

    # ---- standard provider interface (matches every other adapter) ----

    def provider_id(self):
        return self.CONNECTOR_ID

    def provider_name(self):
        return self.PROVIDER_NAME

    def connector_version(self):
        return self._version

    def health_check(self):
        return True

    def retrieve(self, property_id: str):
        mapping = self._mappings.get(property_id)
        if mapping is None:
            self.audit.publish("DCAD_RETRIEVE_BLOCKED", {
                "reason": errors.ACCOUNT_MAPPING_REQUIRED, "property_id": property_id,
            })
            return errors.ACCOUNT_MAPPING_REQUIRED, {}

        if not self._index_store.is_ready(require_info_table=self._join_account_info):
            fetch_status = self._fetch_and_index()
            if fetch_status != errors.PASS:
                self.audit.publish("DCAD_RETRIEVE_BLOCKED", {
                    "reason": fetch_status, "property_id": property_id,
                })
                return fetch_status, {}

        appraisal_row = self._index_store.lookup_appraisal(mapping.account_num, mapping.appraisal_yr)
        if appraisal_row is None:
            self.audit.publish("DCAD_RETRIEVE_BLOCKED", {
                "reason": errors.ACCOUNT_NOT_FOUND, "property_id": property_id,
                "account_num": mapping.account_num,
            })
            return errors.ACCOUNT_NOT_FOUND, {}

        info_row = None
        if self._join_account_info:
            info_row = self._index_store.lookup_info(mapping.account_num, mapping.appraisal_yr)
            if info_row is None:
                # Central record matched, auxiliary record did not --
                # "unmatched central record degrades honestly": proceed
                # with whatever Account_Apprl_Year alone provides,
                # exactly like Phase 1, rather than fail the whole
                # retrieval over a missing auxiliary join.
                self.audit.publish("DCAD_ACCOUNT_INFO_UNMATCHED", {
                    "property_id": property_id, "account_num": mapping.account_num,
                })

        evidence = []
        for era_field, dcad_column in ACCOUNT_APPRL_YEAR_FIELD_MAP.items():
            if era_field == "city" and info_row is not None:
                continue  # PROPERTY_CITY from Account_Info takes priority -- see below
            value = appraisal_row.get(dcad_column)
            if value is not None and str(value).strip() != "":
                evidence.append(ProviderEvidence(field_name=era_field, raw_value=str(value)))
        evidence.append(ProviderEvidence(field_name="state", raw_value=STATE_CONSTANT))

        if info_row is not None:
            city = _clean(info_row.get("PROPERTY_CITY"))
            if city:
                evidence.append(ProviderEvidence(field_name="city", raw_value=city))
            zip_code = _clean(info_row.get("PROPERTY_ZIPCODE"))
            if zip_code:
                evidence.append(ProviderEvidence(field_name="zip_code", raw_value=zip_code))
            address = _build_property_address(info_row)
            if address:
                evidence.append(ProviderEvidence(field_name="property_address", raw_value=address))
            owner = _build_owner_name(info_row)
            if owner:
                evidence.append(ProviderEvidence(field_name="owner_name", raw_value=owner))
            legal = _build_legal_description(info_row)
            if legal:
                evidence.append(ProviderEvidence(field_name="legal_description", raw_value=legal))

        self.audit.publish("DCAD_RETRIEVE_SUCCEEDED", {
            "property_id": property_id, "account_num": mapping.account_num,
            "evidence_count": len(evidence), "joined": info_row is not None,
        })
        return provider_errors.PASS, {
            "evidence": evidence,
            "provenance": {"legal_basis": "PUBLIC_RECORD"},
            "source_reference": (
                f"DCAD-DATA-PRODUCTS-2025-CERTIFIED:{mapping.account_num}:{mapping.appraisal_yr}"
            ),
        }

    def _fetch_and_index(self) -> str:
        """Downloads the ZIP, computes its fingerprint, and rebuilds the
        disk-backed index only if needed (no complete build exists, or
        the source has actually changed). The build itself is delegated
        to DCADIndexStore.build(), which is atomic across both tables in
        one SQL transaction -- see that module for why this supersedes
        the earlier Python-level local-variable staging DCAD-JOIN-001
        originally used to fix the partial-index crash: a real SQL
        transaction protects against process crashes mid-build too, not
        just Python control-flow ordering."""
        client = NetworkClient(self._transport)
        status, payload = client.request_bytes("GET", self._download_url, require_zip=True)
        if status != network_errors.PASS:
            return status

        content = payload["content"]
        self._last_raw_source_bytes = bytes(content)
        fingerprint = compute_fingerprint(content)
        if not self._index_store.needs_rebuild(fingerprint, require_info_table=self._join_account_info):
            self.audit.publish("DCAD_INDEX_REUSED", {"source_fingerprint": fingerprint})
            return errors.PASS

        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile:
            return errors.ZIP_ENTRY_NOT_FOUND

        if self._target_entry_name not in archive.namelist():
            self.audit.publish("DCAD_RETRIEVE_BLOCKED", {
                "reason": errors.ZIP_ENTRY_NOT_FOUND, "target_entry_name": self._target_entry_name,
                "available_entries": archive.namelist()[:20],
            })
            return errors.ZIP_ENTRY_NOT_FOUND
        if self._join_account_info and self._account_info_entry_name not in archive.namelist():
            self.audit.publish("DCAD_RETRIEVE_BLOCKED", {
                "reason": errors.ZIP_ENTRY_NOT_FOUND, "target_entry_name": self._account_info_entry_name,
                "available_entries": archive.namelist()[:20],
            })
            return errors.ZIP_ENTRY_NOT_FOUND

        def appraisal_reader():
            with archive.open(self._target_entry_name) as raw:
                text_stream = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
                yield from csv.DictReader(text_stream)

        info_reader = None
        if self._join_account_info:
            def info_reader():
                with archive.open(self._account_info_entry_name) as raw:
                    text_stream = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
                    yield from csv.DictReader(text_stream)

        try:
            build_result = self._index_store.build(
                appraisal_reader, info_reader, fingerprint,
                REQUIRED_APPRL_YEAR_COLUMNS, REQUIRED_ACCOUNT_INFO_COLUMNS,
            )
        except DCADIndexBuildError as exc:
            self.audit.publish("DCAD_RETRIEVE_BLOCKED", {
                "reason": errors.MALFORMED_CSV_HEADER, "stage": exc.stage, "detail": exc.detail,
            })
            return errors.MALFORMED_CSV_HEADER

        self._duplicate_join_keys["appraisal_year"] = build_result["appraisal_duplicates"]
        self._duplicate_join_keys["account_info"] = build_result["info_duplicates"]
        if build_result["appraisal_duplicates"] or build_result["info_duplicates"]:
            self.audit.publish("DCAD_DUPLICATE_JOIN_KEYS_DETECTED", {
                "appraisal_duplicates": build_result["appraisal_duplicates"],
                "info_duplicates": build_result["info_duplicates"],
            })
        self.audit.publish("DCAD_DATASET_INDEXED", {
            "row_count_appraisal": build_result["appraisal_stored"],
            "row_count_info": build_result["info_stored"],
            "source_fingerprint": fingerprint,
        })
        return errors.PASS

    def get_duplicate_join_key_counts(self) -> dict:
        return dict(self._duplicate_join_keys)

    def attempt_write(self):
        self.audit.publish("DCAD_RETRIEVE_BLOCKED", {"reason": errors.READ_ONLY_ADAPTER})
        return False, errors.READ_ONLY_ADAPTER

    def assign_confidence(self):
        self.audit.publish("DCAD_RETRIEVE_BLOCKED", {"reason": errors.CONFIDENCE_AUTHORITY_VIOLATION})
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
