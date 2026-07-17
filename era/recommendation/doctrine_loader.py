from dataclasses import dataclass
from typing import List
RECOMMENDATION_DOCTRINE_VERSION = "ERA_RECOMMENDATION_DOCTRINE-1.1"
@dataclass(frozen=True)
class RecommendationRule:
    rule_id: str
    recommendation: str
    required_evidence: List[str]
    blocking_conditions: List[str]
    minimum_confidence: str
    methodology_version: str
class DoctrineLoader:
    def load_rules(self) -> List[RecommendationRule]:
        return [
            RecommendationRule(
                rule_id="REC-VERIFY-OCCUPANCY",
                recommendation="Acquire verified occupancy record.",
                required_evidence=["occupancy"],
                blocking_conditions=["missing_decision_trace", "unsupported_evidence"],
                minimum_confidence="PARTIAL",
                methodology_version=RECOMMENDATION_DOCTRINE_VERSION,
            )
        ]
