from enum import Enum
class EvidenceCategory(str, Enum):
    IDENTITY = "IDENTITY"
    OWNERSHIP = "OWNERSHIP"
    PARCEL = "PARCEL"
    LAND = "LAND"
    BUILDING = "BUILDING"
    TAX = "TAX"
    LEGAL = "LEGAL"
    PERMIT = "PERMIT"
    FLOOD = "FLOOD"
    WEATHER = "WEATHER"
    ZONING = "ZONING"
    MARKET = "MARKET"
    DOCUMENT = "DOCUMENT"
    PHOTO = "PHOTO"
    USER_NOTE = "USER_NOTE"
class EvidenceSourceClass(str, Enum):
    PUBLIC_RECORD = "PUBLIC_RECORD"
    PUBLIC_API = "PUBLIC_API"
    LICENSED = "LICENSED"
    LICENSED_REGULATED = "LICENSED_REGULATED"
    USER_PROVIDED = "USER_PROVIDED"
    RESTRICTED = "RESTRICTED"
class EvidenceValueType(str, Enum):
    """
    ECM-TYPE-001: what KIND of value a piece of evidence carries, not
    just what real-world category it belongs to (EvidenceCategory,
    above, is orthogonal to this -- a CURRENCY value can be MARKET or
    TAX category; an IDENTIFIER can be PARCEL or IDENTITY category).

    This is what lets CanonicalEvidenceModel.normalize_record() apply
    the numeric-leakage guard where it's actually meant to apply (free
    TEXT, where a smuggled "confidence=0.95" is a real risk) and skip
    it where it was never meant to apply (a genuine currency value like
    "152500.00", which LOOKS like the leakage pattern but isn't one).

    ECM-OFFICIAL-TEXT-001 added OFFICIAL_TEXT: authoritative free-form
    source text (legal descriptions, deed language, zoning descriptions,
    exemption notes, official remarks) that legitimately contains
    ordinary decimals and percentages -- e.g. real DCAD legal text like
    "BLDG A UNIT 103 & 4.98% CE" -- but should still block genuine
    confidence-vocabulary injection. Distinct from plain TEXT, which
    keeps its full, strict leakage protection unchanged. See
    canonical_engine.py's OFFICIAL_TEXT_LEAK_PATTERNS.
    """
    TEXT = "TEXT"
    OFFICIAL_TEXT = "OFFICIAL_TEXT"
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    CURRENCY = "CURRENCY"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    IDENTIFIER = "IDENTIFIER"
    GEO = "GEO"
    ENUM = "ENUM"
