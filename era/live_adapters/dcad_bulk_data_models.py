from dataclasses import dataclass


@dataclass(frozen=True)
class DCADAccountMapping:
    """The join key between ERA's property_id and DCAD's own identifier.
    DCAD's certified data has no notion of ERA's property_id -- a
    caller (bootstrap, or a future lookup-by-address step) has to
    supply the mapping to ACCOUNT_NUM before retrieve() can find
    anything. This mirrors PropertyIdentity.parcel_apn as the natural
    home for a DCAD ACCOUNT_NUM in ERA's own model, without assuming
    that mapping is automatic."""
    property_id: str
    account_num: str
    appraisal_yr: str = "2025"
