from era.acquisition_execution.verify_ax_adapt001 import run_checks


def test_ax_adapt001_contract():
    failures = [name for name, passed in run_checks().items() if not passed]
    assert not failures, failures

