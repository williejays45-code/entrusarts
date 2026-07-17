from enum import Enum
class DashboardCardType(str, Enum):
    PROPERTY = "PROPERTY"
    EVIDENCE = "EVIDENCE"
    CONFLICT = "CONFLICT"
    DECISION = "DECISION"
    POLICY = "POLICY"
    EXPORT = "EXPORT"
    AUDIT = "AUDIT"
    HEALTH = "HEALTH"
