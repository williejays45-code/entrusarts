"""HA-001 compatibility verification for the finalized authority contract."""

from era.acquisition.verify_health_authority002 import run_checks


checks = run_checks()
for name, passed in checks.items():
    print(f"{name}: {'PASS' if passed else 'FAIL'}")
passed = sum(checks.values())
print(f"HA-001 COMPATIBILITY CHECKS PASSED: {passed}/{len(checks)}")
raise SystemExit(0 if passed == len(checks) else 1)
