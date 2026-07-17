"""Clean-clone safeguard for deliberately fabricated DCAD fallback fixtures."""

from era.live_adapters.dcad_test_data import (
    REAL_DATA_FILENAMES,
    resolve_dcad_test_paths,
    validate_synthetic_fixtures,
)


checks = validate_synthetic_fixtures()
appr_path, info_path, using_full_data = resolve_dcad_test_paths()
checks["fallback_reports_nonproduction_data"] = using_full_data is False
checks["fallback_never_selects_real_excerpt_names"] = REAL_DATA_FILENAMES.isdisjoint({
    __import__("pathlib").Path(appr_path).name,
    __import__("pathlib").Path(info_path).name,
})

for name, passed in checks.items():
    print(f"{name}: {'PASS' if passed else 'FAIL'}")
passed = sum(checks.values())
print(f"DCAD-SYNTHETIC-FIXTURES CHECKS PASSED: {passed}/{len(checks)}")
raise SystemExit(0 if passed == len(checks) else 1)
