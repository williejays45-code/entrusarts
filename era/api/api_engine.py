from era.api.api_audit import ApiAudit
from era.api.api_models import ApiResponse
from era.api import api_errors as errors
from era.auth.auth_enums import AuthPermission
class EraApiEngine:
    """
    AUTH-WIRE-001: every read endpoint below requires a valid,
    non-expired token AND the specific permission listed for that
    endpoint. health() is the one deliberately public endpoint -- it
    takes no token and reveals nothing about any property.

    Endpoint -> required permission:
      get_property / get_evidence / get_decision / get_policy -> READ
      get_export                                               -> EXPORT
      get_audit                                                -> ADMIN
    (FOUNDER holds every permission in MockTokenStore, so a founder
    token satisfies all of the above.)

    No business logic below this line changed: once a caller is
    authorized, every existing lookup/response/audit-publish call is
    exactly what it was before this patch.
    """
    def __init__(self, store, audit=None, auth=None):
        self.store = store
        self.audit = audit or ApiAudit()
        self.auth = auth
    def _authorize(self, token, permission: AuthPermission):
        if self.auth is None:
            # No AuthEngine wired in at all -- fail closed, not open.
            self.audit.publish("API_BLOCKED", {"reason": errors.AUTH_ENGINE_REQUIRED})
            return errors.AUTH_ENGINE_REQUIRED, None
        auth_status, auth_result = self.auth.authenticate(token)
        if auth_status != "PASS":
            self.audit.publish("API_BLOCKED", {"reason": auth_status})
            return auth_status, None
        authz_status = self.auth.authorize(auth_result, permission)
        if authz_status != "PASS":
            self.audit.publish("API_BLOCKED", {
                "reason": authz_status,
                "user_id": auth_result.user_id,
                "permission": permission.value,
            })
            return authz_status, None
        return "PASS", auth_result
    def health(self):
        response = ApiResponse(
            status=errors.PASS,
            endpoint="/health",
            property_id=None,
            data={"service": "ERA API", "healthy": True},
        )
        self.audit.publish("API_REQUEST_RECORDED", {"endpoint": "/health"})
        return errors.PASS, response
    def _require_property(self, property_id):
        if not property_id:
            self.audit.publish("API_BLOCKED", {"reason": errors.PROPERTY_REQUIRED})
            return False
        return True
    def get_property(self, token, property_id):
        authz_status, _ = self._authorize(token, AuthPermission.READ)
        if authz_status != "PASS":
            return authz_status, None
        if not self._require_property(property_id):
            return errors.PROPERTY_REQUIRED, None
        data = self.store.get("properties", {}).get(property_id)
        if data is None:
            self.audit.publish("API_BLOCKED", {"reason": errors.API_NOT_FOUND, "property_id": property_id})
            return errors.API_NOT_FOUND, None
        response = ApiResponse(errors.PASS, f"/property/{property_id}", property_id, data)
        self.audit.publish("API_REQUEST_RECORDED", {"endpoint": "property", "property_id": property_id})
        return errors.PASS, response
    def get_evidence(self, token, property_id):
        authz_status, _ = self._authorize(token, AuthPermission.READ)
        if authz_status != "PASS":
            return authz_status, None
        if not self._require_property(property_id):
            return errors.PROPERTY_REQUIRED, None
        data = self.store.get("evidence", {}).get(property_id)
        if data is None:
            return errors.API_NOT_FOUND, None
        response = ApiResponse(errors.PASS, f"/property/{property_id}/evidence", property_id, {"evidence": data})
        self.audit.publish("API_REQUEST_RECORDED", {"endpoint": "evidence", "property_id": property_id})
        return errors.PASS, response
    def get_decision(self, token, property_id):
        authz_status, _ = self._authorize(token, AuthPermission.READ)
        if authz_status != "PASS":
            return authz_status, None
        if not self._require_property(property_id):
            return errors.PROPERTY_REQUIRED, None
        data = self.store.get("decisions", {}).get(property_id)
        if data is None:
            return errors.API_NOT_FOUND, None
        response = ApiResponse(errors.PASS, f"/property/{property_id}/decision", property_id, data)
        self.audit.publish("API_REQUEST_RECORDED", {"endpoint": "decision", "property_id": property_id})
        return errors.PASS, response
    def get_policy(self, token, property_id):
        authz_status, _ = self._authorize(token, AuthPermission.READ)
        if authz_status != "PASS":
            return authz_status, None
        if not self._require_property(property_id):
            return errors.PROPERTY_REQUIRED, None
        data = self.store.get("policies", {}).get(property_id)
        if data is None:
            return errors.API_NOT_FOUND, None
        response = ApiResponse(errors.PASS, f"/property/{property_id}/policy", property_id, data)
        self.audit.publish("API_REQUEST_RECORDED", {"endpoint": "policy", "property_id": property_id})
        return errors.PASS, response
    def get_export(self, token, property_id):
        authz_status, _ = self._authorize(token, AuthPermission.EXPORT)
        if authz_status != "PASS":
            return authz_status, None
        if not self._require_property(property_id):
            return errors.PROPERTY_REQUIRED, None
        data = self.store.get("exports", {}).get(property_id)
        if data is None:
            return errors.API_NOT_FOUND, None
        response = ApiResponse(errors.PASS, f"/property/{property_id}/export", property_id, data)
        self.audit.publish("API_REQUEST_RECORDED", {"endpoint": "export", "property_id": property_id})
        return errors.PASS, response
    def get_audit(self, token, property_id):
        authz_status, _ = self._authorize(token, AuthPermission.ADMIN)
        if authz_status != "PASS":
            return authz_status, None
        if not self._require_property(property_id):
            return errors.PROPERTY_REQUIRED, None
        data = self.store.get("audits", {}).get(property_id)
        if data is None:
            return errors.API_NOT_FOUND, None
        response = ApiResponse(errors.PASS, f"/property/{property_id}/audit", property_id, {"audit": data})
        self.audit.publish("API_REQUEST_RECORDED", {"endpoint": "audit", "property_id": property_id})
        return errors.PASS, response
    def attempt_write(self):
        self.audit.publish("API_BLOCKED", {"reason": errors.READ_ONLY_API})
        return False, errors.READ_ONLY_API
    def assign_confidence(self):
        self.audit.publish("API_BLOCKED", {"reason": errors.CONFIDENCE_AUTHORITY_VIOLATION})
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
