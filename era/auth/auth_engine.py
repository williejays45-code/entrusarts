from era.auth.auth_audit import AuthAudit
from era.auth.auth_models import AuthResult
from era.auth.auth_enums import AuthPermission
from era.auth.token_store import TokenStore, MockTokenStore
from era.auth.hashed_token_store import HashedTokenStore
from era.auth import auth_errors as errors


class AuthEngine:
    # AUTH-TOKEN-WIRE-001: locked resolution rule. No implicit
    # MockTokenStore fallback anywhere in this class -- MockTokenStore
    # is reachable only two ways: explicit injection (token_store=...),
    # or the explicit use_mock_auth=True escape hatch for tests/dev.
    # The unconfigured default is HashedTokenStore, backed by a real,
    # durable path (auth_db_path) -- not an in-memory, throwaway store,
    # so a production deployment that never thinks about this parameter
    # still gets tokens that survive a restart.
    def __init__(self, token_store: TokenStore = None, audit=None,
                 use_mock_auth: bool = False, auth_db_path: str = "era_auth.db"):
        if token_store is not None:
            resolved_store = token_store
        elif use_mock_auth:
            resolved_store = MockTokenStore()
        else:
            resolved_store = HashedTokenStore(auth_db_path)
        self.token_store = resolved_store
        self.audit = audit or AuthAudit()

    def authenticate(self, token):
        if not token:
            self.audit.publish("AUTH_BLOCKED", {"reason": errors.TOKEN_REQUIRED})
            return errors.TOKEN_REQUIRED, None
        data = self.token_store.lookup(token)
        if data is None:
            self.audit.publish("AUTH_BLOCKED", {"reason": errors.INVALID_TOKEN})
            return errors.INVALID_TOKEN, None
        if data["expired"]:
            self.audit.publish("AUTH_BLOCKED", {"reason": errors.EXPIRED_TOKEN})
            return errors.EXPIRED_TOKEN, None
        result = AuthResult(
            user_id=data["user_id"],
            role=data["role"],
            permissions=list(data["permissions"]),
            authorized=True,
        )
        # Audit payload is user_id/role only -- never the raw token
        # that was passed into this method. This was already true
        # before AUTH-TOKEN-WIRE-001; stated explicitly here because
        # it's now a locked, tested requirement, not an incidental fact.
        self.audit.publish("AUTHENTICATED", {
            "user_id": result.user_id,
            "role": result.role,
        })
        return errors.PASS, result

    def authorize(self, auth_result, permission):
        if auth_result is None or not auth_result.user_id:
            self.audit.publish("AUTH_BLOCKED", {"reason": errors.USER_REQUIRED})
            return errors.USER_REQUIRED
        required = permission.value if hasattr(permission, "value") else permission
        if required not in auth_result.permissions:
            self.audit.publish("AUTH_BLOCKED", {
                "reason": errors.PERMISSION_DENIED,
                "user_id": auth_result.user_id,
                "permission": required,
            })
            return errors.PERMISSION_DENIED
        self.audit.publish("AUTHORIZED", {
            "user_id": auth_result.user_id,
            "permission": required,
        })
        return errors.PASS

    def attempt_write(self):
        self.audit.publish("AUTH_BLOCKED", {"reason": errors.READ_ONLY_AUTH})
        return False, errors.READ_ONLY_AUTH

    def assign_confidence(self):
        self.audit.publish("AUTH_BLOCKED", {
            "reason": errors.CONFIDENCE_AUTHORITY_VIOLATION,
        })
        return False, errors.CONFIDENCE_AUTHORITY_VIOLATION
