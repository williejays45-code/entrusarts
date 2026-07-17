from era.reasoning.verify_ril001 import run_checks


def test_ril001():
    checks = run_checks()
    assert all(checks.values()), {name: passed for name, passed in checks.items() if not passed}
