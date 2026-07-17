from era.evidence_intelligence.verify_eil001 import run_checks


def test_eil001_contract():
    checks = run_checks()
    assert all(checks.values()), [name for name, passed in checks.items() if not passed]
