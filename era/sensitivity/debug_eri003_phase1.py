from era.sensitivity.verify_eri003_phase1 import tests, errors
print("ERI-003.1 DIAGNOSTIC")
print("=" * 70)
passed = 0
for ev_id, expected, fn in tests:
    actual = fn()
    ok = actual == expected
    if ok:
        passed += 1
    print(ev_id)
    print("  EXPECTED:", expected)
    print("  ACTUAL:  ", actual)
    print("  PASS:    ", ok)
    print()
print("DIAGNOSTIC PASSED:", f"{passed}/{len(tests)}")
