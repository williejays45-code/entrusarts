from enum import Enum
class ProviderNetworkStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    REGISTERED = "REGISTERED"
    VERIFIED = "VERIFIED"
    LIVE_TESTED = "LIVE_TESTED"
    OPERATIONAL = "OPERATIONAL"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"
class ProviderNetworkRole(str, Enum):
    CAD = "CAD"
    TAX = "TAX"
    CLERK = "CLERK"
    GIS = "GIS"
    FLOOD = "FLOOD"
    WEATHER = "WEATHER"
