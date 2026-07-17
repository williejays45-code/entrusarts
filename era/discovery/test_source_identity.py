from era.discovery.verify_sdr002 import run_checks


def test_sdr002_contract():
    failures = [name for name, passed in run_checks().items() if not passed]
    assert not failures, failures

