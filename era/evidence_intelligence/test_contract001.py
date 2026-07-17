from era.evidence_intelligence.verify_eil_contract001 import run_checks


def test_eil_contract001():
    failures = [name for name, passed in run_checks().items() if not passed]
    assert not failures, failures

