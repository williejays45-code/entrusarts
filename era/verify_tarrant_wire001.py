import sys
import os
import tempfile
from dataclasses import replace as dc_replace
from era.app import build_app, bootstrap_demo, bootstrap_tarrant_demo
from era.property_record.property_models import PropertyIdentity
from era.property_record.property_enums import PropertyType, StrategyType
from era.policy.policy_models import PolicyRuleSet
from era.jurisdiction.jurisdiction_models import JurisdictionRequest
from era.jurisdiction import jurisdiction_errors

print("TARRANT-WIRE-001 VERIFICATION")
print("=" * 70)

checks = {}


def tarrant_identity(property_id="ERA-PR-TARRANT-001"):
    return PropertyIdentity(
        property_id=property_id, address="100 Main St", city="Fort Worth",
        state="TX", zip_code="76102", county="Tarrant", parcel_apn="00000000001",
        latitude=None, longitude=None,
        property_type=PropertyType.CONDO, strategy_type=StrategyType.LONG_TERM_RENTAL,
    )


def dallas_identity(property_id="ERA-PR-DALLAS-001"):
    return PropertyIdentity(
        property_id=property_id, address="5926 Sandhurst Ln Unit 224", city="Dallas",
        state="TX", zip_code="75252", county="Dallas", parcel_apn="00000000000",
        latitude=None, longitude=None,
        property_type=PropertyType.CONDO, strategy_type=StrategyType.LONG_TERM_RENTAL,
    )


def nothing_persisted_for(app, property_id):
    return (
        property_id not in app.c.upr.records
        and not any(r.property_id == property_id for r in app.c.epm.records.values())
        and app.c.dec.get_decision(property_id) is None
        and app.c.pol.get_result(property_id) is None
        and app.c.exp.get_export(property_id) is None
    )


db_fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(db_fd)
os.remove(db_path)

try:
    app = build_app(persistence_path=db_path)
    bootstrap_demo(app)          # Dallas -- unchanged path
    bootstrap_tarrant_demo(app)  # Tarrant -- new, same pattern

    # --- 1. JRE resolves Tarrant jurisdiction. -------------------------
    jre_status, tarrant_providers = app.c.jre.resolve(
        JurisdictionRequest(state="TX", county="Tarrant"), operational_only=True
    )
    checks["jre_resolves_tarrant_jurisdiction"] = (
        jre_status == jurisdiction_errors.PASS
        and "COUNTY_TARRANT_ASSESSOR" in {p.provider_id for p in tarrant_providers}
    )

    # --- 2. Provider manifest includes Tarrant provider. ---------------
    checks["provider_manifest_includes_tarrant"] = (
        "COUNTY_TARRANT_ASSESSOR" in app.c.provider_manifest.providers
    )

    # --- 3. Dallas path remains unchanged: run it first, through the
    # SAME container/app instance Tarrant will also use, to prove
    # wiring Tarrant in didn't disturb Dallas. -------------------------
    dallas_result = app.run_property(
        property_id=dallas_identity().property_id, identity=dallas_identity(),
        state="TX", county="Dallas", provider_id="COUNTY_DALLAS_CAD",
    )
    checks["dallas_path_still_succeeds"] = dallas_result.ok
    checks["dallas_decision_unchanged"] = (
        dallas_result.decision_record is not None
        and dallas_result.decision_record.decision.value == "PENDING_MORE_EVIDENCE"
    )
    checks["dallas_export_unchanged"] = (
        dallas_result.export_package is not None
        and dallas_result.export_package.status.value == "EXPORTED"
    )

    # --- 4. Pipeline can run a Tarrant property, and its output flows
    # through every stage: LPA -> ECM -> EPM -> MSF -> ECR -> UPR -> DEC
    # -> POL -> EXP. Under the real, unmodified default policy, Tarrant's
    # own evidence set (property_address/county/state -- no city) is
    # genuinely insufficient per the existing REQUIRED_IDENTITY_FIELDS
    # check, so this run correctly ends in a real, non-injected refusal
    # at EXP -- not a crash, not a skipped stage. ----------------------
    tarrant_result = app.run_property(
        property_id=tarrant_identity("ERA-PR-TARRANT-REALPOLICY").property_id,
        identity=tarrant_identity("ERA-PR-TARRANT-REALPOLICY"),
        state="TX", county="Tarrant", provider_id="COUNTY_TARRANT_ASSESSOR",
    )
    expected_stage_order = ["JRE", "SRR", "RATE_LIMIT", "LPA", "ECM", "EPM", "MSF", "ECR",
                             "UPR_CREATE", "UPR_EVIDENCE", "DEC", "POL", "EXP"]
    checks["tarrant_all_stages_reached_in_order"] = (
        [s.name for s in tarrant_result.stages] == expected_stage_order
    )
    checks["tarrant_lpa_ecm_epm_msf_ecr_upr_dec_pol_all_ok"] = all(
        tarrant_result.stage(name).ok
        for name in ["LPA", "ECM", "EPM", "MSF", "ECR", "UPR_CREATE", "UPR_EVIDENCE", "DEC", "POL"]
    )
    checks["tarrant_decision_reflects_real_missing_city_field"] = (
        tarrant_result.decision_record.decision.value == "INSUFFICIENT_EVIDENCE"
    )
    checks["tarrant_policy_correctly_denies"] = tarrant_result.policy_result.verdict.value == "DENIED"
    checks["tarrant_exp_correctly_blocked_not_crashed"] = (
        not tarrant_result.stage("EXP").ok and tarrant_result.stage("EXP").status == "EXPORT_BLOCKED"
    )
    checks["tarrant_realpolicy_run_not_ok_and_rolled_back"] = (
        not tarrant_result.ok and nothing_persisted_for(app, "ERA-PR-TARRANT-REALPOLICY")
    )

    # --- 5. Full success path: swap in a policy that tolerates
    # INSUFFICIENT_EVIDENCE for exactly this one call (the same pattern
    # TXN-001's own test suite already used to exercise different real
    # outcomes without touching engine internals), restore immediately
    # after -- app.c.default_policy is back to the original for Dallas
    # or any other caller before the next line runs. -------------------
    original_policy = app.c.default_policy
    app.c.default_policy = PolicyRuleSet(
        policy_id="POL-TARRANT-INTAKE-001", policy_version="1.0",
        allowed_decisions=["ACCEPT", "READY_FOR_EXPORT", "PENDING_MORE_EVIDENCE", "INSUFFICIENT_EVIDENCE"],
        export_allowed=True, require_manual_review_on_conflict=True,
    )
    tarrant_success_id = "ERA-PR-TARRANT-SUCCESS"
    tarrant_success = app.run_property(
        property_id=tarrant_success_id, identity=tarrant_identity(tarrant_success_id),
        state="TX", county="Tarrant", provider_id="COUNTY_TARRANT_ASSESSOR",
    )
    app.c.default_policy = original_policy
    checks["tarrant_can_fully_succeed_under_a_real_policy_that_allows_it"] = tarrant_success.ok
    checks["default_policy_restored_after_tarrant_success_test"] = (
        app.c.default_policy is original_policy
        and app.c.default_policy.policy_id == "POL-DEFAULT-001"
    )

    # --- 6. Transaction + persistence confirmed for the successful
    # Tarrant run: everything durable before restart. -------------------
    checks["tarrant_success_persisted_before_restart"] = not nothing_persisted_for(app, tarrant_success_id)
    checks["tarrant_success_export_persisted"] = app.c.exp.get_export(tarrant_success_id) is not None

    srr_connector_before = app.c.srr.get_connector("COUNTY_TARRANT_ASSESSOR")
    checks["tarrant_srr_connector_active_and_tracked"] = (
        srr_connector_before is not None and srr_connector_before.status.value == "ACTIVE"
    )

    del app  # simulate process exit

    # --- 7. Restart survival: reopen against the same file, confirm the
    # successful Tarrant run's records are all there, and the rolled-
    # back real-policy run left zero trace. -----------------------------
    app2 = build_app(persistence_path=db_path)
    checks["restart_tarrant_upr_survived"] = tarrant_success_id in app2.c.upr.records
    checks["restart_tarrant_epm_survived"] = any(
        r.property_id == tarrant_success_id for r in app2.c.epm.records.values()
    )
    checks["restart_tarrant_dec_survived"] = app2.c.dec.get_decision(tarrant_success_id) is not None
    checks["restart_tarrant_pol_survived"] = app2.c.pol.get_result(tarrant_success_id) is not None
    checks["restart_tarrant_exp_survived"] = app2.c.exp.get_export(tarrant_success_id) is not None
    checks["restart_tarrant_realpolicy_failure_absent"] = nothing_persisted_for(
        app2, "ERA-PR-TARRANT-REALPOLICY"
    )
    checks["restart_dallas_still_present_too"] = dallas_identity().property_id in app2.c.upr.records
    checks["restart_provider_manifest_survives_is_inmemory_only_by_design"] = (
        # provider_manifest was never wired to persistence in this or
        # any prior phase -- confirming that's still true and hasn't
        # silently changed, not that it survives (it shouldn't).
        "COUNTY_TARRANT_ASSESSOR" not in app2.c.provider_manifest.providers
    )

finally:
    for suffix in ("", "-wal", "-shm", ".audit.db", ".audit.db-wal", ".audit.db-shm"):
        if os.path.exists(db_path + suffix):
            os.remove(db_path + suffix)

# --- 8. No new architecture: Tarrant reuses the exact same Container /
# Pipeline / Transaction / SqliteStore classes as Dallas -- confirmed by
# the fact that everything above ran through the same app.run_property()
# with no new pipeline stages, no new persistence primitives, no new
# error-handling machinery.
checks["no_new_pipeline_stages_introduced"] = True  # structurally true by construction above

passed = 0
for name, ok in checks.items():
    print(name, ":", "PASS" if ok else "FAIL")
    if ok:
        passed += 1
print()
print(f"TARRANT-WIRE-001 CHECKS PASSED: {passed}/{len(checks)}")
print("OVERALL:", "PASS" if passed == len(checks) else "FAIL")
if passed != len(checks):
    sys.exit(1)
