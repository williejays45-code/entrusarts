from era.acquisition.verify_health_authority002 import run_checks


def test_all_required_health_authority_behaviors():
    failures = [name for name, passed in run_checks().items() if not passed]
    assert failures == []
