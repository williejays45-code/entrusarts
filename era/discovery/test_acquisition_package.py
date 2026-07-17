from era.discovery.verify_sdr004 import run_checks


def test_sdr004_contract():
    failures = [name for name, passed in run_checks().items() if not passed]
    assert not failures, failures

