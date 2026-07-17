"""
SPINE-002: Composition Root, part 3 -- the entry point.

Run this file directly (`python -m era.app`) and it will wire a real
Container, register a real jurisdiction and a real connector, and run
one property end to end through all 13 pipeline stages, printing what
happened at each step. This is the thing that did not exist anywhere in
the original archive: one place, that when run, actually builds the
system instead of defining 20 classes nothing ever instantiates
together.
"""

from era.container import Container
from era.pipeline import Pipeline
from era.shared.persistence import SqliteStore
from era.acquisition.connector_models import ConnectorRecord, ResourcePolicy, RetryPolicy
from era.acquisition.connector_enums import LegalClassification, ConnectorStatus, ConnectorCategory
from era.jurisdiction.jurisdiction_models import JurisdictionProvider
from era.jurisdiction.jurisdiction_enums import ProviderOperationalStatus, ProviderRole
from era.property_record.property_models import PropertyIdentity
from era.property_record.property_enums import PropertyType, StrategyType


def build_app(persistence_path: str = None, token_store=None, dcad_download_url: str = None,
              dcad_join_account_info: bool = False, dcad_index_db_path: str = "dcad_index.db",
              use_mock_auth: bool = False, auth_db_path: str = "era_auth.db",
              collin_mdb_path: str = None, collin_code_list_path: str = None) -> Pipeline:
    """The composition root. Everything the system needs is wired here
    and nowhere else. Pass persistence_path to back SRR with real SQLite
    persistence (see C4); leave it None for a clean in-memory run.

    Auth (AUTH-TOKEN-WIRE-001 locked resolution rule):
    - token_store=<a TokenStore> -- explicit injection, wins over
      everything else. Tests that construct their own MockTokenStore
      or a fake TokenStore use this.
    - use_mock_auth=True -- convenience flag for tests/dev that just
      want the four known fixed tokens without constructing
      MockTokenStore themselves.
    - Neither given -- the real default: HashedTokenStore backed by
      auth_db_path (a real, durable file, not in-memory-only). This is
      what a production deployment gets if it never thinks about this
      parameter at all.

    Pass dcad_download_url to register the DCAD bulk data adapter (see
    LIVE-ADAPTER-001B) -- leave it None and that provider simply isn't
    registered; no placeholder URL is ever assumed. Pass
    dcad_join_account_info=True to additionally join Account_Info (see
    DCAD-JOIN-001) -- leave it False for Phase 1 behavior only. Pass
    dcad_index_db_path to control where the disk-backed DCAD index
    lives (see DCAD-INDEX-001) -- defaults to a stable path so real
    usage reuses the index across restarts as intended; tests that need
    isolation from each other should pass a distinct temp path here."""
    store = SqliteStore(persistence_path) if persistence_path else None
    container = Container(persistence_store=store, token_store=token_store,
                           dcad_download_url=dcad_download_url,
                           dcad_join_account_info=dcad_join_account_info,
                           dcad_index_db_path=dcad_index_db_path,
                           use_mock_auth=use_mock_auth, auth_db_path=auth_db_path,
                           collin_mdb_path=collin_mdb_path,
                           collin_code_list_path=collin_code_list_path)
    return Pipeline(container)


def bootstrap_demo(pipeline: Pipeline):
    """Registers the jurisdiction + connector the demo run below needs.
    A real deployment would do this once, out of band, not on every run."""
    pipeline.bootstrap_jurisdiction(
        state="TX", county="Dallas",
        providers=[
            JurisdictionProvider(
                provider_id="COUNTY_DALLAS_CAD",
                provider_name="Dallas Central Appraisal District",
                role=ProviderRole.CAD,
                status=ProviderOperationalStatus.OPERATIONAL,
            )
        ],
    )
    connector = ConnectorRecord(
        connector_id="COUNTY_DALLAS_CAD",
        provider_name="Dallas Central Appraisal District",
        version="1.0",
        category=ConnectorCategory.COUNTY_PUBLIC_RECORDS,
        legal_classification=LegalClassification.PUBLIC_RECORD,
        status=ConnectorStatus.ACTIVE,
        capabilities=["OWNERSHIP", "PARCEL"],
        resource_policy=ResourcePolicy(
            refresh_schedule_hours=24, rate_limit_per_day=500,
            cache_duration_hours=24, monthly_budget_limit=0.0, max_requests=500,
        ),
        retry_policy=RetryPolicy(max_retries=2, retry_delay_seconds=10),
    )
    pipeline.c.srr.register_connector(connector)


def bootstrap_tarrant_demo(pipeline: Pipeline):
    """
    TARRANT-WIRE-001: registers the jurisdiction + connector + provider
    manifest entry a Tarrant run needs. Kept entirely separate from
    bootstrap_demo() (Dallas) so the Dallas path is untouched by this --
    same pattern, new function, not a modification of the existing one.
    """
    pipeline.bootstrap_jurisdiction(
        state="TX", county="Tarrant",
        providers=[
            JurisdictionProvider(
                provider_id="COUNTY_TARRANT_ASSESSOR",
                provider_name="Tarrant County Assessor",
                role=ProviderRole.CAD,
                status=ProviderOperationalStatus.OPERATIONAL,
            )
        ],
    )
    connector = ConnectorRecord(
        connector_id="COUNTY_TARRANT_ASSESSOR",
        provider_name="Tarrant County Assessor",
        version="1.0",
        category=ConnectorCategory.COUNTY_PUBLIC_RECORDS,
        legal_classification=LegalClassification.PUBLIC_RECORD,
        status=ConnectorStatus.ACTIVE,
        capabilities=["OWNERSHIP", "PARCEL", "TAX_ASSESSMENT"],
        resource_policy=ResourcePolicy(
            refresh_schedule_hours=24, rate_limit_per_day=500,
            cache_duration_hours=24, monthly_budget_limit=0.0, max_requests=500,
        ),
        retry_policy=RetryPolicy(max_retries=2, retry_delay_seconds=10),
    )
    pipeline.c.srr.register_connector(connector)

    # "Provider manifest includes Tarrant provider" -- ProviderManifest
    # was already wired for persistence (AUDIT-persistence rollout) but
    # nothing had ever registered an entry in it; this is the first one.
    from era.provider_network.provider_manifest_models import ProviderManifestEntry, ProviderHealth
    from era.provider_network.provider_manifest_enums import ProviderNetworkStatus, ProviderNetworkRole
    pipeline.c.provider_manifest.register_provider(ProviderManifestEntry(
        provider_id="COUNTY_TARRANT_ASSESSOR", provider_name="Tarrant County Assessor",
        state="TX", county="Tarrant", role=ProviderNetworkRole.CAD,
        status=ProviderNetworkStatus.OPERATIONAL, public=True, read_only=True,
        legal_basis="PUBLIC_RECORD", version="1.0",
        health=ProviderHealth(success_rate=1.0, latency_ms=120, failures=0),
    ))


def bootstrap_collin_demo(pipeline: Pipeline):
    """CCS-001: register the opt-in Collin bulk MDB provider."""
    pipeline.bootstrap_jurisdiction(
        state="TX", county="Collin",
        providers=[
            JurisdictionProvider(
                provider_id="COLLIN_BULK_MDB",
                provider_name="Collin Central Appraisal District",
                role=ProviderRole.CAD,
                status=ProviderOperationalStatus.OPERATIONAL,
            )
        ],
    )
    connector = ConnectorRecord(
        connector_id="COLLIN_BULK_MDB",
        provider_name="Collin Central Appraisal District",
        version="2026-preliminary",
        category=ConnectorCategory.COUNTY_PUBLIC_RECORDS,
        legal_classification=LegalClassification.PUBLIC_RECORD,
        status=ConnectorStatus.ACTIVE,
        capabilities=["OWNERSHIP", "PARCEL", "TAX_ASSESSMENT"],
        resource_policy=ResourcePolicy(
            refresh_schedule_hours=24, rate_limit_per_day=500,
            cache_duration_hours=24, monthly_budget_limit=0.0, max_requests=500,
        ),
        retry_policy=RetryPolicy(max_retries=0, retry_delay_seconds=0),
    )
    pipeline.c.srr.register_connector(connector)

    from era.provider_network.provider_manifest_models import ProviderManifestEntry, ProviderHealth
    from era.provider_network.provider_manifest_enums import ProviderNetworkStatus, ProviderNetworkRole
    pipeline.c.provider_manifest.register_provider(ProviderManifestEntry(
        provider_id="COLLIN_BULK_MDB", provider_name="Collin Central Appraisal District",
        state="TX", county="Collin", role=ProviderNetworkRole.CAD,
        status=ProviderNetworkStatus.OPERATIONAL, public=True, read_only=True,
        legal_basis="PUBLIC_RECORD", version="2026-preliminary",
        health=ProviderHealth(success_rate=1.0, latency_ms=0, failures=0),
    ))


def bootstrap_manual_demo(pipeline: Pipeline):
    """
    LIVE-ADAPTER-001A: registers the jurisdiction + connector entry a
    manual-capture run needs. Separate from bootstrap_demo() (Dallas)
    and bootstrap_tarrant_demo() (Tarrant) -- same pattern, its own
    function, neither of the other two touched.
    """
    pipeline.bootstrap_jurisdiction(
        state="TX", county="Dallas",
        providers=[
            JurisdictionProvider(
                provider_id="MANUAL_RECORD_CAPTURE",
                provider_name="Manual Public-Record Capture",
                role=ProviderRole.CAD,
                status=ProviderOperationalStatus.OPERATIONAL,
            )
        ],
    )
    connector = ConnectorRecord(
        connector_id="MANUAL_RECORD_CAPTURE",
        provider_name="Manual Public-Record Capture",
        version="1.0",
        category=ConnectorCategory.COUNTY_PUBLIC_RECORDS,
        legal_classification=LegalClassification.PUBLIC_RECORD,
        status=ConnectorStatus.ACTIVE,
        capabilities=["OWNERSHIP", "PARCEL"],
        resource_policy=ResourcePolicy(
            refresh_schedule_hours=24, rate_limit_per_day=500,
            cache_duration_hours=24, monthly_budget_limit=0.0, max_requests=500,
        ),
        retry_policy=RetryPolicy(max_retries=2, retry_delay_seconds=10),
    )
    pipeline.c.srr.register_connector(connector)


def bootstrap_dcad_demo(pipeline: Pipeline):
    """
    LIVE-ADAPTER-001B: registers the jurisdiction + SRR connector entry
    a DCAD bulk-data run needs. Requires pipeline.c.dcad_bulk_data_adapter
    to already exist -- i.e. build_app() must have been called with a
    real dcad_download_url. Does NOT register any property's account
    mapping; call pipeline.c.dcad_bulk_data_adapter.register_account_mapping()
    per property separately, same staging pattern as the manual adapter.
    """
    if pipeline.c.dcad_bulk_data_adapter is None:
        raise RuntimeError(
            "bootstrap_dcad_demo() requires build_app(dcad_download_url=...) "
            "-- the DCAD adapter is not registered without a real URL."
        )
    pipeline.bootstrap_jurisdiction(
        state="TX", county="Dallas",
        providers=[
            JurisdictionProvider(
                provider_id="DCAD_BULK_DATA_2025",
                provider_name="DCAD Data Products - 2025 Certified Data Files",
                role=ProviderRole.CAD,
                status=ProviderOperationalStatus.OPERATIONAL,
            )
        ],
    )
    connector = ConnectorRecord(
        connector_id="DCAD_BULK_DATA_2025",
        provider_name="DCAD Data Products - 2025 Certified Data Files",
        version="2025-certified",
        category=ConnectorCategory.COUNTY_PUBLIC_RECORDS,
        legal_classification=LegalClassification.PUBLIC_RECORD,
        status=ConnectorStatus.ACTIVE,
        capabilities=["OWNERSHIP", "PARCEL", "TAX_ASSESSMENT"],
        resource_policy=ResourcePolicy(
            refresh_schedule_hours=24, rate_limit_per_day=10,
            cache_duration_hours=24, monthly_budget_limit=0.0, max_requests=10,
        ),
        retry_policy=RetryPolicy(max_retries=2, retry_delay_seconds=15),
    )
    pipeline.c.srr.register_connector(connector)


if __name__ == "__main__":
    app = build_app()
    bootstrap_demo(app)

    identity = PropertyIdentity(
        property_id="ERA-PR-2026-000001",
        address="5926 Sandhurst Ln Unit 224", city="Dallas", state="TX",
        zip_code="75252", county="Dallas", parcel_apn="00000000000",
        latitude=None, longitude=None,
        property_type=PropertyType.CONDO, strategy_type=StrategyType.LONG_TERM_RENTAL,
    )

    result = app.run_property(
        property_id=identity.property_id, identity=identity,
        state="TX", county="Dallas", provider_id="COUNTY_DALLAS_CAD",
    )

    print("ERA SPINE-002 -- COMPOSITION ROOT DEMO RUN")
    print("=" * 70)
    for s in result.stages:
        print(f"  [{ 'OK' if s.ok else 'FAIL'}] {s.name}: {s.status}")
    print()
    print("PIPELINE OK:", result.ok)
    if result.decision_record:
        print("DECISION:", result.decision_record.decision.value)
    if result.policy_result:
        print("POLICY VERDICT:", result.policy_result.verdict.value)
    if result.export_package:
        print("EXPORT STATUS:", result.export_package.status.value)
