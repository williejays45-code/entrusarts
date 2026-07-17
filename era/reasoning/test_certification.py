"""Focused pytest wrapper for RIL-CERT-WIRE-001."""

from era.reasoning.verify_ril_cert_wire001 import run_checks


def test_ril_cert_wire001():
    assert all(run_checks().values())
