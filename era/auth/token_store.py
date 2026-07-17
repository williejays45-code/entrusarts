"""
Token verification is pluggable. AuthEngine no longer hardcodes tokens
directly — it depends on a TokenStore interface.

MockTokenStore below is the exact same four literal tokens that used to
live inline in AuthEngine ("user-token", "admin-token", "founder-token",
"expired-token"). It is unchanged behaviorally, but it is now clearly
named as a mock, isolated in its own file, and NOT the default a
production caller falls into by accident — AuthEngine.__init__ requires
a token_store to be passed explicitly.

Before AuthEngine is used for anything real (anything DAVID MASS,
EnTrus Core, or ERA depends on for actual access control), MockTokenStore
must be replaced with a real implementation of TokenStore backed by
signed/hashed tokens (e.g. JWT verification, a hashed-token DB lookup,
or a real identity provider) with real expiry timestamps instead of a
static boolean flag.
"""

from abc import ABC, abstractmethod


class TokenStore(ABC):
    """Interface AuthEngine depends on. Implement this for real auth."""

    @abstractmethod
    def lookup(self, token: str):
        """Return a dict with keys user_id, role, permissions, expired,
        or None if the token is unrecognized."""
        raise NotImplementedError


class MockTokenStore(TokenStore):
    """TEST/DEV ONLY. Do not use in any environment with real user data
    or real authorization consequences. Tokens are static plaintext
    strings with no signature, no hashing, and no real expiry."""

    _TOKENS = {
        "user-token": {
            "user_id": "USER-001",
            "role": "USER",
            "permissions": ["READ"],
            "expired": False,
        },
        "admin-token": {
            "user_id": "ADMIN-001",
            "role": "ADMIN",
            "permissions": ["READ", "EXPORT", "ADMIN"],
            "expired": False,
        },
        "founder-token": {
            "user_id": "FOUNDER-001",
            "role": "FOUNDER",
            "permissions": ["READ", "EXPORT", "ADMIN", "FOUNDER"],
            "expired": False,
        },
        "expired-token": {
            "user_id": "USER-EXPIRED",
            "role": "USER",
            "permissions": ["READ"],
            "expired": True,
        },
    }

    def lookup(self, token: str):
        return self._TOKENS.get(token)
