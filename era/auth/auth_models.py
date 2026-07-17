from dataclasses import dataclass, field
from datetime import datetime, timezone
from era.auth.auth_enums import AuthRole
def utc_now():
    return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class AuthToken:
    token: str
    user_id: str
    role: AuthRole
    permissions: list
    expired: bool = False
@dataclass(frozen=True)
class AuthResult:
    user_id: str
    role: AuthRole
    permissions: list
    authorized: bool
    created_at: str = field(default_factory=utc_now)
