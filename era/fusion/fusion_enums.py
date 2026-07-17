from enum import Enum
class FusionStatus(str, Enum):
    CONSENSUS = "CONSENSUS"
    CONFLICT = "CONFLICT"
    SINGLE_SOURCE = "SINGLE_SOURCE"
