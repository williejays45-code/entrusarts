from enum import Enum
class ProviderOperationalStatus(str, Enum):
    REGISTERED = "REGISTERED"
    VERIFIED = "VERIFIED"
    OPERATIONAL = "OPERATIONAL"
    DISABLED = "DISABLED"
    NOT_OPERATIONAL = "NOT_OPERATIONAL"
class ProviderRole(str, Enum):
    CAD = "CAD"
    TAX = "TAX"
    CLERK = "CLERK"
    GIS = "GIS"
    FLOOD = "FLOOD"
    WEATHER = "WEATHER"
