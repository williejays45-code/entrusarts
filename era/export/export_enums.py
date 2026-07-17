from enum import Enum
class ExportStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    EXPORTED = "EXPORTED"
    FAILED = "FAILED"
class ExportFormat(str, Enum):
    JSON = "JSON"
    CSV = "CSV"
    PDF = "PDF"
    API = "API"
    DASHBOARD = "DASHBOARD"
    PARTNER = "PARTNER"
