import sys
import os
import tempfile
from era.app import build_app, bootstrap_demo
from era.property_record.property_models import PropertyIdentity
from era.property_record.property_enums import PropertyType, StrategyType
from era.policy.policy_models import PolicyRuleSet
from era.decision import decision_errors

print("TXN-001 VERIFICATION -- pipeline-level transaction boundary")
print("=" * 70)

checks = {}


def make_identity(property_id):
    return PropertyIdentity(
        property_id=property_id, address="5926 Sandhurst Ln Unit 224", city="Dallas",
        state="TX", zip_code="75252", county="Dallas", parcel_apn="00000000000",
        latitude=None, longitude=None,
        property_type=PropertyType.CONDO, strategy_type=StrategyType.LONG_TERM_RENTAL,
    )


def nothing_persisted_for(app, property_id):
    """True if none of the 7 persisted engines have any durable trace of
    this property -- the actual cross-engine atomicity claim."""
    return (
        property_id not in app.c.upr.records
        and not any(r.property_id == property_id for r in app.c.epm.records.values())
        and not any(r.property_id == property_id for r in app.c.ecr.reports.values())
        and app.c.dec.get_decision(property_id) is None
        and app.c.pol.get_result(property_id) is None
        and app.c.exp.get_export(property_id) is None
    )


db_fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(db_fd)
os.remove(db_path)

try:
    app = build_app(persistence_path=db_path)
    bootstrap_demo(app)
    connector_before = app.c.srr.get_connector("COUNTY_DALLAS_CAD")
    success_count_before = connector_before.success_count

    # --- Scenario 1: force a genuine DEC failure. --------------------
    # DEC can't be made to fail through real data once EPM has already
    # required non-empty evidence upstream, so this is deliberate fault
    # injection on the DecisionEngine instance -- same spirit as
    # BrokenStore in verify_persistence_error_handling.py -- restored
    # immediately after. Everything upstream of DEC (SRR/LPA/ECM/EPM/
    # MSF/ECR/UPR) runs for real and genuinely attempts to persist
    # inside the same transaction before DEC is reached.
    original_decide = app.c.dec.decide

    def broken_decide(item, conn=None):
        return decision_errors.PROPERTY_REQUIRED, None

    app.c.dec.decide = broken_decide
    identity_dec = make_identity("ERA-PR-TXN-DEC-FAIL")
    result_dec = app.run_property(
        property_id=identity_dec.property_id, identity=identity_dec,
        state="TX", county="Dallas", provider_id="COUNTY_DALLAS_CAD",
    )
    app.c.dec.decide = original_decide

    checks["dec_failure_pipeline_not_ok"] = not result_dec.ok
    checks["dec_failure_stage_recorded_as_failed"] = (
        result_dec.stage("DEC") is not None and not result_dec.stage("DEC").ok
    )
    checks["dec_failure_nothing_persisted"] = nothing_persisted_for(app, "ERA-PR-TXN-DEC-FAIL")
    # UPR/EPM/ECR all genuinely ran and would have committed under the
    # old (pre-TXN-001) per-call-autocommit behavior -- this is the
    # actual regression TXN-001 closes, confirmed by checking they
    # really did attempt work before the rollback.
    checks["dec_failure_upstream_stages_actually_ran"] = (
        result_dec.stage("EPM") is not None and result_dec.stage("EPM").ok
        and result_dec.stage("UPR_EVIDENCE") is not None and result_dec.stage("UPR_EVIDENCE").ok
    )

    # --- Scenario 2: force a genuine POL failure. ---------------------
    # This one needs no monkeypatching -- an invalid policy_id is a real
    # PolicyEngine.evaluate() validation failure. DEC succeeds for real
    # and genuinely writes inside the transaction before POL aborts it.
    original_policy = app.c.default_policy
    app.c.default_policy = PolicyRuleSet(
        policy_id="", policy_version="1.0",
        allowed_decisions=["ACCEPT", "READY_FOR_EXPORT", "PENDING_MORE_EVIDENCE"],
        export_allowed=True, require_manual_review_on_conflict=True,
    )
    identity_pol = make_identity("ERA-PR-TXN-POL-FAIL")
    result_pol = app.run_property(
        property_id=identity_pol.property_id, identity=identity_pol,
        state="TX", county="Dallas", provider_id="COUNTY_DALLAS_CAD",
    )
    app.c.default_policy = original_policy

    checks["pol_failure_pipeline_not_ok"] = not result_pol.ok
    checks["pol_failure_stage_recorded_as_failed"] = (
        result_pol.stage("POL") is not None and not result_pol.stage("POL").ok
    )
    checks["pol_failure_dec_stage_actually_succeeded_before_rollback"] = (
        result_pol.stage("DEC") is not None and result_pol.stage("DEC").ok
    )
    checks["pol_failure_nothing_persisted"] = nothing_persisted_for(app, "ERA-PR-TXN-POL-FAIL")

    # --- Scenario 3: force a genuine EXP failure. ---------------------
    # export_allowed=False is real PolicyEngine business logic -- POL
    # itself succeeds (returns a real EXPORT_DENIED-verdict PolicyResult
    # and writes it inside the transaction), then ExportEngine.export()
    # genuinely rejects that verdict as unauthorized.
    original_export_allowed = app.c.default_policy.export_allowed
    from dataclasses import replace as dc_replace
    app.c.default_policy = dc_replace(app.c.default_policy, export_allowed=False)
    identity_exp = make_identity("ERA-PR-TXN-EXP-FAIL")
    result_exp = app.run_property(
        property_id=identity_exp.property_id, identity=identity_exp,
        state="TX", county="Dallas", provider_id="COUNTY_DALLAS_CAD",
    )
    app.c.default_policy = dc_replace(app.c.default_policy, export_allowed=original_export_allowed)

    checks["exp_failure_pipeline_not_ok"] = not result_exp.ok
    checks["exp_failure_stage_recorded_as_failed"] = (
        result_exp.stage("EXP") is not None and not result_exp.stage("EXP").ok
    )
    checks["exp_failure_pol_stage_actually_succeeded_before_rollback"] = (
        result_exp.stage("POL") is not None and result_exp.stage("POL").ok
    )
    checks["exp_failure_nothing_persisted"] = nothing_persisted_for(app, "ERA-PR-TXN-EXP-FAIL")

    # --- SRR side-effect check: the connector's success_count bump from
    # each of the three failed runs above must also have rolled back --
    # it's inside the same transaction, not a separate concern. ---
    connector_after_failures = app.c.srr.get_connector("COUNTY_DALLAS_CAD")
    checks["srr_success_count_unaffected_by_rolled_back_runs"] = (
        connector_after_failures.success_count == success_count_before
    )

    # --- Scenario 4: full success must still commit everything. -------
    identity_ok = make_identity("ERA-PR-TXN-SUCCESS")
    result_ok = app.run_property(
        property_id=identity_ok.property_id, identity=identity_ok,
        state="TX", county="Dallas", provider_id="COUNTY_DALLAS_CAD",
    )
    checks["success_run_ok"] = result_ok.ok
    checks["success_run_all_persisted_before_restart"] = not nothing_persisted_for(app, "ERA-PR-TXN-SUCCESS")
    checks["success_run_srr_success_count_incremented"] = (
        app.c.srr.get_connector("COUNTY_DALLAS_CAD").success_count == success_count_before + 1
    )
    del app  # simulate process exit

    # --- Restart-survival success test (explicitly requested): reopen
    # against the same file, confirm the successful run's records are
    # all still there, and the three rolled-back runs left no trace. ---
    app2 = build_app(persistence_path=db_path)
    checks["restart_success_upr_survived"] = "ERA-PR-TXN-SUCCESS" in app2.c.upr.records
    checks["restart_success_epm_survived"] = any(
        r.property_id == "ERA-PR-TXN-SUCCESS" for r in app2.c.epm.records.values()
    )
    checks["restart_success_dec_survived"] = app2.c.dec.get_decision("ERA-PR-TXN-SUCCESS") is not None
    checks["restart_success_pol_survived"] = app2.c.pol.get_result("ERA-PR-TXN-SUCCESS") is not None
    checks["restart_success_exp_survived"] = app2.c.exp.get_export("ERA-PR-TXN-SUCCESS") is not None
    checks["restart_confirms_dec_failure_run_absent"] = nothing_persisted_for(app2, "ERA-PR-TXN-DEC-FAIL")
    checks["restart_confirms_pol_failure_run_absent"] = nothing_persisted_for(app2, "ERA-PR-TXN-POL-FAIL")
    checks["restart_confirms_exp_failure_run_absent"] = nothing_persisted_for(app2, "ERA-PR-TXN-EXP-FAIL")
    checks["restart_srr_success_count_matches_only_the_one_real_success"] = (
        app2.c.srr.get_connector("COUNTY_DALLAS_CAD").success_count == success_count_before + 1
    )

    # --- No-persistence mode is completely unaffected by TXN-001. -----
    plain_app = build_app()
    bootstrap_demo(plain_app)
    identity_plain = make_identity("ERA-PR-TXN-PLAIN")
    plain_result = plain_app.run_property(
        property_id=identity_plain.property_id, identity=identity_plain,
        state="TX", county="Dallas", provider_id="COUNTY_DALLAS_CAD",
    )
    checks["no_persistence_mode_still_works"] = plain_result.ok
    checks["no_persistence_mode_has_no_store"] = plain_app.c.persistence_store is None

finally:
    for suffix in ("", "-wal", "-shm", ".audit.db", ".audit.db-wal", ".audit.db-shm"):
        if os.path.exists(db_path + suffix):
            os.remove(db_path + suffix)

passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print(f"TXN-001 CHECKS PASSED: {passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
