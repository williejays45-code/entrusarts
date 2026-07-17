from era.dashboard.dashboard_audit import DashboardAudit
from era.dashboard.dashboard_models import DashboardCard, DashboardView
from era.dashboard.dashboard_enums import DashboardCardType
from era.dashboard import dashboard_errors as errors
class DashboardEngine:
    REQUIRED_KEYS = [
        "property",
        "evidence",
        "conflicts",
        "decision",
        "policy",
        "export",
        "audit",
        "health",
    ]
    def __init__(self, audit=None):
        self.audit = audit or DashboardAudit()
    def build_dashboard(self, property_id, data):
        if not property_id:
            self.audit.publish("DASHBOARD_BLOCKED", {"reason": errors.PROPERTY_REQUIRED})
            return errors.PROPERTY_REQUIRED, None
        if not data:
            self.audit.publish("DASHBOARD_BLOCKED", {"reason": errors.DASHBOARD_DATA_REQUIRED})
            return errors.DASHBOARD_DATA_REQUIRED, None
        for key in self.REQUIRED_KEYS:
            if key not in data:
                self.audit.publish("DASHBOARD_BLOCKED", {
                    "reason": errors.CARD_REQUIRED,
                    "missing_card": key,
                })
                return errors.CARD_REQUIRED, None
        cards = [
            DashboardCard(DashboardCardType.PROPERTY, "Property Summary", dict(data["property"])),
            DashboardCard(DashboardCardType.EVIDENCE, "Evidence Timeline", dict(data["evidence"])),
            DashboardCard(DashboardCardType.CONFLICT, "Conflict Viewer", dict(data["conflicts"])),
            DashboardCard(DashboardCardType.DECISION, "Decision Viewer", dict(data["decision"])),
            DashboardCard(DashboardCardType.POLICY, "Policy Viewer", dict(data["policy"])),
            DashboardCard(DashboardCardType.EXPORT, "Export Center", dict(data["export"])),
            DashboardCard(DashboardCardType.AUDIT, "Audit Timeline", dict(data["audit"])),
            DashboardCard(DashboardCardType.HEALTH, "System Health", dict(data["health"])),
        ]
        view = DashboardView(
            property_id=property_id,
            cards=cards,
        )
        self.audit.publish("DASHBOARD_BUILT", {
            "property_id": property_id,
            "card_count": len(cards),
        })
        self.audit.publish("DASHBOARD_READY", {
            "property_id": property_id,
        })
        return errors.PASS, view
    def attempt_write(self):
        self.audit.publish("DASHBOARD_BLOCKED", {"reason": errors.READ_ONLY_DASHBOARD})
        return False, errors.READ_ONLY_DASHBOARD
    def assign_confidence(self):
        self.audit.publish("DASHBOARD_BLOCKED", {
            "reason": errors.CONFIDENCE_AUTHORITY_VIOLATION,
        })
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
