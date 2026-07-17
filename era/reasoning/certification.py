"""RIL-CERT-WIRE-001 immutable operation-local certification projections."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
import hashlib
import json


CERTIFICATION_CONTRACT_VERSION = "1"


def _json_ready(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, Decimal)):
        return str(value)
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_ready(item) for item in value]
    return value


def _digest(material) -> str:
    encoded = json.dumps(
        _json_ready(material), sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def rule_fingerprint(rule) -> str:
    """Fingerprint the complete semantic rule definition, not only its ID."""
    return _digest({"kind": "RIL_RULE", "rule": rule})


def policy_constraint_fingerprint(constraint) -> str:
    """Fingerprint the complete policy constraint projection."""
    return _digest({"kind": "RIL_POLICY_CONSTRAINT", "constraint": constraint})


def _required(*values):
    if any(value is None or (isinstance(value, str) and not value.strip()) for value in values):
        raise ValueError("CERTIFICATION_VALUE_REQUIRED")


def _validate_fingerprints(values):
    if not isinstance(values, tuple) or not values:
        raise ValueError("IMMUTABLE_CERTIFICATION_FINGERPRINTS_REQUIRED")
    if tuple(sorted(values)) != values or len(values) != len(set(values)):
        raise ValueError("CERTIFICATION_FINGERPRINTS_MUST_BE_SORTED_UNIQUE")
    if any(
        len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
        for value in values
    ):
        raise ValueError("INVALID_CERTIFICATION_FINGERPRINT")


@dataclass(frozen=True)
class RuleCertificationProjection:
    certification_id: str
    certification_version: str
    authority_reference: str
    rule_fingerprints: tuple[str, ...]
    projection_digest: str
    contract_version: str = CERTIFICATION_CONTRACT_VERSION

    def __post_init__(self):
        _required(
            self.certification_id, self.certification_version,
            self.authority_reference, self.projection_digest, self.contract_version,
        )
        if self.contract_version != CERTIFICATION_CONTRACT_VERSION:
            raise ValueError("UNKNOWN_CERTIFICATION_CONTRACT_VERSION")
        _validate_fingerprints(self.rule_fingerprints)
        if self.projection_digest != self._expected_digest():
            raise ValueError("RULE_CERTIFICATION_DIGEST_MISMATCH")

    @classmethod
    def issue(cls, certification_id, certification_version, authority_reference, rules):
        fingerprints = tuple(sorted(rule_fingerprint(rule) for rule in rules))
        material = {
            "kind": "RIL_RULE_CERTIFICATION",
            "contract_version": CERTIFICATION_CONTRACT_VERSION,
            "certification_id": certification_id,
            "certification_version": certification_version,
            "authority_reference": authority_reference,
            "rule_fingerprints": fingerprints,
        }
        return cls(
            certification_id, certification_version, authority_reference,
            fingerprints, _digest(material),
        )

    def _expected_digest(self):
        return _digest({
            "kind": "RIL_RULE_CERTIFICATION",
            "contract_version": self.contract_version,
            "certification_id": self.certification_id,
            "certification_version": self.certification_version,
            "authority_reference": self.authority_reference,
            "rule_fingerprints": self.rule_fingerprints,
        })

    def authorizes(self, rules) -> bool:
        try:
            supplied = tuple(sorted(rule_fingerprint(rule) for rule in rules))
        except (TypeError, ValueError):
            return False
        return supplied == self.rule_fingerprints


@dataclass(frozen=True)
class PolicyCertificationProjection:
    certification_id: str
    certification_version: str
    authority_reference: str
    policy_id: str
    policy_version: str
    constraint_fingerprints: tuple[str, ...]
    projection_digest: str
    contract_version: str = CERTIFICATION_CONTRACT_VERSION

    def __post_init__(self):
        _required(
            self.certification_id, self.certification_version,
            self.authority_reference, self.policy_id, self.policy_version,
            self.projection_digest, self.contract_version,
        )
        if self.contract_version != CERTIFICATION_CONTRACT_VERSION:
            raise ValueError("UNKNOWN_CERTIFICATION_CONTRACT_VERSION")
        _validate_fingerprints(self.constraint_fingerprints)
        if self.projection_digest != self._expected_digest():
            raise ValueError("POLICY_CERTIFICATION_DIGEST_MISMATCH")

    @classmethod
    def issue(
        cls, certification_id, certification_version, authority_reference,
        policy_id, policy_version, constraints,
    ):
        fingerprints = tuple(sorted(
            policy_constraint_fingerprint(item) for item in constraints
        ))
        material = {
            "kind": "RIL_POLICY_CERTIFICATION",
            "contract_version": CERTIFICATION_CONTRACT_VERSION,
            "certification_id": certification_id,
            "certification_version": certification_version,
            "authority_reference": authority_reference,
            "policy_id": policy_id,
            "policy_version": policy_version,
            "constraint_fingerprints": fingerprints,
        }
        return cls(
            certification_id, certification_version, authority_reference,
            policy_id, policy_version, fingerprints, _digest(material),
        )

    def _expected_digest(self):
        return _digest({
            "kind": "RIL_POLICY_CERTIFICATION",
            "contract_version": self.contract_version,
            "certification_id": self.certification_id,
            "certification_version": self.certification_version,
            "authority_reference": self.authority_reference,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "constraint_fingerprints": self.constraint_fingerprints,
        })

    def authorizes(self, constraints, context) -> bool:
        try:
            supplied = tuple(sorted(
                policy_constraint_fingerprint(item) for item in constraints
            ))
        except (TypeError, ValueError):
            return False
        return (
            supplied == self.constraint_fingerprints
            and context.policy_id == self.policy_id
            and context.policy_version == self.policy_version
        )
