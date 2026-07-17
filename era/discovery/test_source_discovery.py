from era.discovery.verify_sdr001 import run_checks


def test_sdr001_contract():
    failures = [name for name, passed in run_checks().items() if not passed]
    assert not failures, failures

