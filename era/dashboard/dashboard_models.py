from dataclasses import dataclass, field
from datetime import datetime, timezone
from era.dashboard.dashboard_enums import DashboardCardType
def utc_now():
    return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class DashboardCard:
    card_type: DashboardCardType
    title: str
    data: dict
@dataclass(frozen=True)
class DashboardView:
    property_id: str
    cards: list
    created_at: str = field(default_factory=utc_now)
