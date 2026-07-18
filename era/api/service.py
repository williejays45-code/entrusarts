"""Loopback-oriented FastAPI boundary for the verified ERA property operator."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import re
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from era.api.api_audit import ApiAudit
from era.auth.auth_engine import AuthEngine
from era.auth.auth_enums import AuthPermission
from era.auth.token_store import TokenStore
from era.run_property import PROVIDER_ROUTES, execute_operator


MAX_REQUEST_BYTES = 4096
MAX_SELECTOR_LENGTH = 256
DEFAULT_TIMEOUT_SECONDS = 120.0
CORRELATION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class EnvironmentTokenStore(TokenStore):
    """One runtime-configured bearer token, retained only as a SHA-256 digest."""

    def __init__(self, token):
        self._digest = hashlib.sha256(token.encode()).digest() if token else None

    def lookup(self, token):
        if self._digest is None or not token:
            return None
        candidate = hashlib.sha256(token.encode()).digest()
        if not hmac.compare_digest(candidate, self._digest):
            return None
        return {"user_id": "ERA-API-OPERATOR", "role": "OPERATOR", "permissions": ["READ"], "expired": False}


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    provider: str = Field(min_length=1, max_length=32)
    county: str | None = Field(default=None, max_length=64)
    account_id: str | None = Field(default=None, max_length=MAX_SELECTOR_LENGTH)
    address: str | None = Field(default=None, max_length=MAX_SELECTOR_LENGTH)

    @model_validator(mode="after")
    def exactly_one_selector(self):
        if bool(self.account_id) == bool(self.address):
            raise ValueError("EXACTLY_ONE_SELECTOR_REQUIRED")
        return self


def correlation_id(external):
    if external and CORRELATION_PATTERN.fullmatch(external):
        return external
    return f"era-{uuid.uuid4().hex}"


def error_response(code, correlation, status, message="Request rejected"):
    return JSONResponse(status_code=status, content={
        "error": {"code": code, "message": message, "correlation_id": correlation}
    })


class EraPropertyApiService:
    def __init__(self, environ=None, operator=execute_operator, audit=None):
        self.environ = os.environ if environ is None else environ
        self.operator = operator
        self.audit = audit or ApiAudit()
        self.auth = AuthEngine(
            token_store=EnvironmentTokenStore(self.environ.get("ERA_API_BEARER_TOKEN"))
        )

    def health(self):
        return {
            "service": "ERA Property Analysis API",
            "status": "ok",
            "version": self.environ.get("ERA_SERVICE_VERSION"),
            "supported_providers": sorted(PROVIDER_ROUTES),
            "utc": datetime.now(timezone.utc).isoformat(),
        }

    def authorize(self, authorization, correlation):
        if not authorization or not authorization.startswith("Bearer "):
            self.audit.publish("API_ANALYZE_DENIED", {"reason": "BEARER_REQUIRED", "correlation_id": correlation})
            return "BEARER_REQUIRED"
        token = authorization[7:]
        status, auth_result = self.auth.authenticate(token)
        if status != "PASS" or self.auth.authorize(auth_result, AuthPermission.READ) != "PASS":
            self.audit.publish("API_ANALYZE_DENIED", {"reason": "AUTHENTICATION_FAILED", "correlation_id": correlation})
            return "AUTHENTICATION_FAILED"
        return None

    def analyze(self, item: AnalyzeRequest, authorization, correlation):
        auth_error = self.authorize(authorization, correlation)
        if auth_error:
            raise PermissionError(auth_error)
        try:
            report = self.operator(
                item.provider, item.account_id, environ=self.environ,
                address=item.address, county=item.county or "Collin",
            )
        except ValueError as exc:
            code = str(exc).split(";", 1)[0]
            self.audit.publish("API_ANALYZE_DENIED", {"reason": code, "correlation_id": correlation})
            raise ValueError(code) from exc
        if not report.get("ok"):
            code = report.get("resolution", {}).get("status") or report.get("acquisition_status") or "ANALYSIS_FAILED"
            self.audit.publish("API_ANALYZE_DENIED", {"reason": code, "correlation_id": correlation})
            raise RuntimeError(code)
        report = dict(report)
        report["correlation_id"] = correlation
        self.audit.publish("API_ANALYZE_ALLOWED", {
            "correlation_id": correlation, "provider": report["provider"],
            "jurisdiction": report["jurisdiction"], "run_id": report["run_id"],
        })
        return report


def create_app(environ=None, operator=execute_operator, audit=None):
    service = EraPropertyApiService(environ=environ, operator=operator, audit=audit)
    api = FastAPI(title="ERA Property Analysis API", docs_url=None, redoc_url=None, openapi_url=None)
    api.state.era_service = service

    @api.exception_handler(RequestValidationError)
    async def validation_error(request, _exc):
        cid = correlation_id(request.headers.get("x-request-id"))
        return error_response("INVALID_REQUEST", cid, 422)

    @api.middleware("http")
    async def request_limit(request: Request, call_next):
        cid = correlation_id(request.headers.get("x-request-id"))
        request.state.correlation_id = cid
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > MAX_REQUEST_BYTES):
            service.audit.publish("API_ANALYZE_DENIED", {"reason": "REQUEST_TOO_LARGE", "correlation_id": cid})
            return error_response("REQUEST_TOO_LARGE", cid, 413)
        return await call_next(request)

    @api.get("/healthz")
    async def healthz():
        return service.health()

    @api.post("/v1/property/analyze")
    async def analyze(request: Request, item: AnalyzeRequest, authorization: str | None = Header(default=None)):
        cid = request.state.correlation_id
        try:
            timeout = float(service.environ.get("ERA_API_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
            return await asyncio.wait_for(
                asyncio.to_thread(service.analyze, item, authorization, cid), timeout=timeout
            )
        except PermissionError as exc:
            return error_response(str(exc), cid, 401, "Authentication failed")
        except asyncio.TimeoutError:
            service.audit.publish("API_ANALYZE_DENIED", {"reason": "TIMEOUT", "correlation_id": cid})
            return error_response("TIMEOUT", cid, 504)
        except ValueError as exc:
            return error_response(str(exc), cid, 422)
        except RuntimeError as exc:
            code = str(exc).split(":", 1)[0]
            status = 404 if code.endswith("NOT_FOUND") else 409 if code.endswith("AMBIGUOUS") else 503
            return error_response(code, cid, status, "Analysis unavailable")
        except Exception:
            service.audit.publish("API_ANALYZE_DENIED", {"reason": "INTERNAL_ERROR", "correlation_id": cid})
            return error_response("INTERNAL_ERROR", cid, 500, "Internal failure")

    return api


app = create_app()
