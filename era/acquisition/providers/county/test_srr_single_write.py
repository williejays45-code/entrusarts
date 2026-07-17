import os
import tempfile

from era.acquisition.acquisition_provider import AcquisitionProvider
from era.app import build_app, bootstrap_demo, bootstrap_tarrant_demo
from era.policy.policy_models import PolicyRuleSet
from era.property_record.property_enums import PropertyType, StrategyType
from era.property_record.property_models import PropertyIdentity


TARRANT = "COUNTY_TARRANT_ASSESSOR"
DALLAS = "COUNTY_DALLAS_CAD"


def identity(property_id, county="Tarrant"):
    return PropertyIdentity(
        property_id=property_id,
        address="100 Main St",
        city=county,
        state="TX",
        zip_code="76000",
        county=county,
        parcel_apn="0001",
        latitude=None,
        longitude=None,
        property_type=PropertyType.CONDO,
        strategy_type=StrategyType.LONG_TERM_RENTAL,
    )


def allow_tarrant_success(app):
    app.c.default_policy = PolicyRuleSet(
        policy_id="POL-TARRANT-TEST",
        policy_version="1.0",
        allowed_decisions=[
            "ACCEPT",
            "READY_FOR_EXPORT",
            "PENDING_MORE_EVIDENCE",
            "INSUFFICIENT_EVIDENCE",
        ],
        export_allowed=True,
        require_manual_review_on_conflict=True,
    )


def test_adapters_expose_common_acquisition_contract():
    app = build_app(use_mock_auth=True)
    for provider_id in (DALLAS, TARRANT):
        adapter = app.c.county_connectors[provider_id]
        assert isinstance(adapter, AcquisitionProvider)
        assert adapter.provider_id() == provider_id
        assert adapter.provider_name()
        assert adapter.connector_version()


def test_configured_collin_adapter_exposes_common_acquisition_contract():
    app = build_app(
        use_mock_auth=True,
        collin_mdb_path="contract-only-AD_Public.mdb",
        collin_code_list_path="contract-only-CodeFileLists.xls",
    )
    adapter = app.c.county_connectors["COLLIN_BULK_MDB"]
    assert isinstance(adapter, AcquisitionProvider)
    assert adapter.provider_id() == "COLLIN_BULK_MDB"
    assert adapter.provider_name() == "Collin Central Appraisal District"
    assert adapter.connector_version()


def test_successful_tarrant_pipeline_run_records_one_success():
    app = build_app(use_mock_auth=True)
    bootstrap_tarrant_demo(app)
    allow_tarrant_success(app)

    before = app.c.srr.get_connector(TARRANT).success_count
    result = app.run_property("TARRANT-ONE-SUCCESS", identity("TARRANT-ONE-SUCCESS"), "TX", "Tarrant", TARRANT)
    after = app.c.srr.get_connector(TARRANT).success_count

    assert result.ok
    assert after - before == 1


def test_failed_tarrant_acquisition_records_one_failure_in_memory():
    app = build_app(use_mock_auth=True)
    bootstrap_tarrant_demo(app)
    connector = app.c.county_connectors[TARRANT]._connector
    connector._retrieve_public_record_stub = lambda request: []

    before = app.c.srr.get_connector(TARRANT).failure_count
    result = app.run_property("TARRANT-ONE-FAILURE", identity("TARRANT-ONE-FAILURE"), "TX", "Tarrant", TARRANT)
    after = app.c.srr.get_connector(TARRANT).failure_count

    assert not result.ok
    assert after - before == 1


def test_persistent_pipeline_rollback_leaves_no_premature_tarrant_success():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    try:
        app = build_app(persistence_path=path, use_mock_auth=True)
        bootstrap_tarrant_demo(app)
        before = app.c.srr.get_connector(TARRANT).success_count

        result = app.run_property("TARRANT-ROLLBACK", identity("TARRANT-ROLLBACK"), "TX", "Tarrant", TARRANT)

        assert not result.ok
        assert app.c.srr.get_connector(TARRANT).success_count == before
        restarted = build_app(persistence_path=path, use_mock_auth=True)
        assert restarted.c.srr.get_connector(TARRANT).success_count == before
    finally:
        for suffix in ("", "-wal", "-shm", ".audit.db", ".audit.db-wal", ".audit.db-shm"):
            candidate = path + suffix
            if os.path.exists(candidate):
                os.remove(candidate)


def test_dallas_pipeline_success_count_remains_one_per_run():
    app = build_app(use_mock_auth=True)
    bootstrap_demo(app)

    before = app.c.srr.get_connector(DALLAS).success_count
    result = app.run_property("DALLAS-ONE-SUCCESS", identity("DALLAS-ONE-SUCCESS", "Dallas"), "TX", "Dallas", DALLAS)
    after = app.c.srr.get_connector(DALLAS).success_count

    assert result.ok
    assert after - before == 1
