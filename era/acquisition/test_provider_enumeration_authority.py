from era.acquisition.verify_provider_enumeration001 import run_checks


def test_provider_enumeration_authority_contract():
    failures = [name for name, passed in run_checks().items() if not passed]
    assert failures == []
