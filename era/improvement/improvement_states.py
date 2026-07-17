from enum import Enum
class ImpactLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    MINIMAL = "MINIMAL"
class ImprovementStatus(str, Enum):
    PENDING = "PENDING"
    VALIDATED = "VALIDATED"
    BLOCKED = "BLOCKED"
