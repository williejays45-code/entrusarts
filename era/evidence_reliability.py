from dataclasses import dataclass
from datetime import datetime, timezone
from era.shared.confidence import CONFIDENCE_ORDER as STATUS_RANK, effective_confidence
METHODOLOGY_VERSION = "ERA_RELIABILITY_METHODOLOGY-1.0"
CATEGORY_STATUS = {
    "government_record": "VERIFIED",
    "legal_record": "VERIFIED",
    "financial_record": "VALIDATED",
    "market_data": "ESTIMATED",
    "inspection": "VALIDATED",
    "owner_statement": "ESTIMATED",
    "sensor_data": "ESTIMATED",
    "ai_inference": "PLACEHOLDER",
    "external_ai": "PLACEHOLDER",
    "unknown": "UNSUPPORTED",
}
@dataclass
class EvidenceItem:
    evidence_id: str
    category: str
    source: str
    attribute: str
    value: str
    methodology_version: str
    factors: dict
@dataclass
class EvidenceEvaluation:
    evidence_id: str
    category: str
    status: str
    reliability_score: float
    confidence: str
    reason: str
    methodology_version: str
    evaluated_at: str
def _factor_score(factors: dict) -> float:
    if not factors:
        return 0.0
    values = []
    for value in factors.values():
        if isinstance(value, bool):
            values.append(1.0 if value else 0.0)
        elif isinstance(value, (int, float)):
            values.append(max(0.0, min(1.0, float(value))))
        else:
            values.append(0.0)
    if not values:
        return 0.0
    return round((sum(values) / len(values)) * 100, 2)
def evaluate_evidence(item: EvidenceItem) -> EvidenceEvaluation:
    category = str(item.category).lower().strip()
    if item.methodology_version != METHODOLOGY_VERSION:
        return EvidenceEvaluation(
            evidence_id=item.evidence_id,
            category=category,
            status="UNSUPPORTED",
            reliability_score=0.0,
            confidence="UNSUPPORTED",
            reason="METHODOLOGY_VERSION_MISMATCH",
            methodology_version=item.methodology_version,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )
    if category not in CATEGORY_STATUS:
        return EvidenceEvaluation(
            evidence_id=item.evidence_id,
            category=category,
            status="UNSUPPORTED",
            reliability_score=0.0,
            confidence="UNSUPPORTED",
            reason="UNKNOWN_EVIDENCE_TYPE",
            methodology_version=item.methodology_version,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )
    status = CATEGORY_STATUS[category]
    if status == "UNSUPPORTED":
        return EvidenceEvaluation(
            evidence_id=item.evidence_id,
            category=category,
            status="UNSUPPORTED",
            reliability_score=0.0,
            confidence="UNSUPPORTED",
            reason="UNSUPPORTED_CATEGORY",
            methodology_version=item.methodology_version,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )
    score = _factor_score(item.factors)
    if not item.factors.get("chain_of_custody", False):
        score = round(score * 0.75, 2)
    confidence = effective_confidence(status)
    if category in {"ai_inference", "external_ai"}:
        confidence = effective_confidence(confidence, "PLACEHOLDER")
    return EvidenceEvaluation(
        evidence_id=item.evidence_id,
        category=category,
        status=status,
        reliability_score=score,
        confidence=confidence,
        reason="EVALUATED",
        methodology_version=item.methodology_version,
        evaluated_at=datetime.now(timezone.utc).isoformat(),
    )
def detect_contradiction(evaluations: list[EvidenceItem]) -> dict:
    grouped = {}
    for item in evaluations:
        key = item.attribute
        grouped.setdefault(key, set()).add(str(item.value).lower().strip())
    conflicts = {
        attribute: values
        for attribute, values in grouped.items()
        if len(values) > 1
    }
    if conflicts:
        return {
            "conflict": True,
            "reason": "CONFLICTING_EVIDENCE",
            "conflicts": conflicts,
        }
    return {
        "conflict": False,
        "reason": "NO_CONFLICT",
        "conflicts": {},
    }
