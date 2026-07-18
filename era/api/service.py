"""Loopback-oriented FastAPI boundary for the verified ERA property operator."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import inspect
import json
import os
import re
import time
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
from era.pipeline import OperationCancelled
from era.run_property import PROVIDER_ROUTES, execute_operator
from era.acquisition.supplemental_evidence import EVIDENCE_SCHEMAS
from era.api.isolated_worker import MAX_CANDIDATE_BYTES, PROTOCOL
from era.api.process_boundary import OwnedProcessBoundary
from era.api.admission_store import (
    AdmissionCancelled, AdmissionExpired, AdmissionIntent, AdmissionStore,
)


MAX_REQUEST_BYTES = 4096
MAX_SELECTOR_LENGTH = 256
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_QUIESCENCE_SECONDS = 0.25
MIN_QUIESCENCE_SECONDS = 0.10
MAX_QUIESCENCE_SECONDS = 2.0
CORRELATION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class IsolatedExecutionTimeout(RuntimeError):
    pass


class IsolatedExecutionFailure(RuntimeError):
    pass


class RequestSupervisor:
    """Cancellation handle for controller threads; owns no commit authority."""

    def __init__(self):
        import threading
        self._lock = threading.Lock()
        self._cancelled = threading.Event()
        self._active = None

    @property
    def cancelled(self):
        return self._cancelled.is_set()

    def activate(self, boundary, closure_seconds):
        with self._lock:
            self._active = boundary
            cancelled = self._cancelled.is_set()
        if cancelled:
            boundary.cancel(closure_seconds)

    def deactivate(self, boundary):
        with self._lock:
            if self._active is boundary:
                self._active = None

    def cancel(self, closure_seconds):
        self._cancelled.set()
        with self._lock:
            boundary = self._active
        return True if boundary is None else boundary.cancel(closure_seconds)

    def wait_closed(self, timeout):
        with self._lock:
            boundary = self._active
        return True if boundary is None else boundary.wait_closed(timeout)


class SupplementalEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)
    evidence_type: str = Field(min_length=1, max_length=64)
    source_class: str = Field(min_length=1, max_length=32)
    observation_utc: str = Field(min_length=1, max_length=40)
    evidence_digest: str = Field(pattern=r"^[A-Fa-f0-9]{64}$")
    verification_status: str = Field(min_length=1, max_length=16)
    facts: dict[str, int | float | str] = Field(min_length=1, max_length=12)

    @model_validator(mode="before")
    @classmethod
    def reject_boolean_facts(cls, data):
        if isinstance(data, dict) and isinstance(data.get("facts"), dict):
            if any(isinstance(value, bool) for value in data["facts"].values()):
                raise ValueError("BOOLEAN_FACT_PROHIBITED")
            schema = EVIDENCE_SCHEMAS.get(str(data.get("evidence_type", "")).lower())
            if schema:
                for name, value in data["facts"].items():
                    rule = schema["fields"].get(name)
                    if (rule and rule["kind"] in {"number", "integer"}
                            and isinstance(value, str) and value != value.strip()):
                        raise ValueError("NUMERIC_WHITESPACE_PROHIBITED")
        return data


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
    supplemental_evidence: list[SupplementalEvidenceRequest] | None = Field(
        default=None, max_length=8,
    )

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
    def __init__(self, environ=None, operator=execute_operator, audit=None,
                 process_boundary_factory=OwnedProcessBoundary,
                 worker_test_mode=None, worker_test_controls=None,
                 validation_delay_seconds=0, admission_delay_seconds=0,
                 admission_store=None):
        self.environ = os.environ if environ is None else environ
        self.operator = operator
        self.audit = audit or ApiAudit()
        self.process_boundary_factory = process_boundary_factory
        self.worker_test_mode = worker_test_mode
        self.worker_test_controls = dict(worker_test_controls or {})
        self.validation_delay_seconds = float(validation_delay_seconds)
        self.admission_delay_seconds = float(admission_delay_seconds)
        admission_path = self.environ.get("ERA_API_ADMISSION_DB_PATH")
        self.admission_store = admission_store or (
            AdmissionStore(admission_path) if admission_path
            else AdmissionStore(":memory:") if worker_test_mode else None
        )
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

    def _operator_arguments(self, item):
        return {
            "environ": self.environ,
            "address": item.address,
            "county": item.county or "Collin",
            "supplemental_evidence": [
                evidence.model_dump() for evidence in (item.supplemental_evidence or ())
            ],
        }

    def _admit_report(self, item, correlation, report):
        if not isinstance(report, dict):
            raise RuntimeError("ANALYSIS_FAILED")
        if not report.get("ok"):
            resolution_status = report.get("resolution", {}).get("status")
            supplemental = report.get("supplemental_evidence", {})
            acquisition_status = report.get("acquisition_status")
            if resolution_status not in {None, "PASS", "ACCOUNT_ID_SUPPLIED"}:
                code = resolution_status
            elif supplemental.get("conflict_count", 0):
                code = "SUPPLEMENTAL_EVIDENCE_CONFLICT"
            elif acquisition_status not in {None, "PASS"}:
                code = acquisition_status
            else:
                code = "ANALYSIS_FAILED"
            self.audit.publish(
                "API_ANALYZE_DENIED", {"reason": code, "correlation_id": correlation},
            )
            raise RuntimeError(code)
        report = dict(report)
        report["correlation_id"] = correlation
        self.audit.publish("API_ANALYZE_ALLOWED", {
            "correlation_id": correlation, "provider": report["provider"],
            "jurisdiction": report["jurisdiction"], "run_id": report["run_id"],
            "supplemental_evidence_count": len(item.supplemental_evidence or ()),
        })
        return report

    def analyze(self, item: AnalyzeRequest, authorization, correlation, operation_control=None):
        """Synchronous composition seam retained for non-HTTP fabricated checks.

        The FastAPI endpoint never calls this method; operational HTTP execution
        always uses :meth:`analyze_isolated`.
        """
        auth_error = self.authorize(authorization, correlation)
        if auth_error:
            raise PermissionError(auth_error)
        try:
            kwargs = self._operator_arguments(item)
            parameters = inspect.signature(self.operator).parameters
            if ("operation_control" in parameters
                    or any(value.kind == inspect.Parameter.VAR_KEYWORD
                           for value in parameters.values())):
                kwargs["operation_control"] = operation_control
            report = self.operator(item.provider, item.account_id, **kwargs)
        except ValueError as exc:
            code = str(exc).split(";", 1)[0]
            self.audit.publish(
                "API_ANALYZE_DENIED", {"reason": code, "correlation_id": correlation},
            )
            raise ValueError(code) from exc
        return self._admit_report(item, correlation, report)

    @staticmethod
    def _encode_worker_request(payload):
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("ascii")

    @staticmethod
    def _decode_worker_response(raw, expected_status):
        if not raw or len(raw) > MAX_CANDIDATE_BYTES:
            raise IsolatedExecutionFailure("WORKER_IPC_INVALID")
        class DuplicateKey(ValueError):
            pass
        def reject_duplicates(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise DuplicateKey("IPC_DUPLICATE_KEY")
                result[key] = value
            return result
        try:
            response = json.loads(raw.decode("ascii"), object_pairs_hook=reject_duplicates)
        except (UnicodeDecodeError, json.JSONDecodeError, DuplicateKey) as exc:
            raise IsolatedExecutionFailure("WORKER_IPC_INVALID") from exc
        if not isinstance(response, dict) or response.get("protocol") != PROTOCOL:
            raise IsolatedExecutionFailure("WORKER_IPC_INVALID")
        status = response.get("status")
        schemas = {
            "CANDIDATE": {"protocol", "status", "candidate"},
            "ERROR": {"protocol", "status", "reason_code"},
        }
        if status not in expected_status or status not in schemas or set(response) != schemas[status]:
            raise IsolatedExecutionFailure("WORKER_IPC_INVALID")
        if status == "CANDIDATE" and not isinstance(response["candidate"], dict):
            raise IsolatedExecutionFailure("WORKER_IPC_INVALID")
        if status == "ERROR" and not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", response["reason_code"]):
            raise IsolatedExecutionFailure("WORKER_IPC_INVALID")
        return response

    def _run_owned_stage(self, payload, deadline, closure_seconds, supervisor):
        remaining = deadline - time.monotonic()
        if remaining <= 0 or supervisor.cancelled:
            raise IsolatedExecutionTimeout("TIMEOUT")
        boundary = self.process_boundary_factory()
        supervisor.activate(boundary, closure_seconds)
        try:
            try:
                result = boundary.run(
                    self._encode_worker_request(payload), remaining, closure_seconds,
                )
            except Exception as exc:
                raise IsolatedExecutionFailure("WORKER_CONTROLLER_FAILED") from exc
        finally:
            supervisor.deactivate(boundary)
        if result.outcome == "TIMEOUT" and result.tree_closed:
            raise IsolatedExecutionTimeout("TIMEOUT")
        if result.outcome == "CANCELLED" and result.tree_closed:
            raise AdmissionCancelled("ADMISSION_CANCELLED")
        if result.outcome != "COMPLETED" or not result.tree_closed:
            raise IsolatedExecutionFailure("WORKER_CONTAINMENT_FAILED")
        return result.stdout

    def _authorized_without_audit(self, authorization):
        if not authorization or not authorization.startswith("Bearer "):
            return False
        status, result = self.auth.authenticate(authorization[7:])
        return status == "PASS" and self.auth.authorize(result, AuthPermission.READ) == "PASS"

    def analyze_isolated(self, item, authorization, correlation, timeout, closure_seconds,
                         supervisor):
        """Compute and validate in owned processes; admit only in this parent."""
        auth_error = self.authorize(authorization, correlation)
        if auth_error:
            raise PermissionError(auth_error)
        deadline = time.monotonic() + timeout
        item_payload = item.model_dump(mode="json")
        operator_environment = {
            key: self.environ.get(key) for key in (
                "ERA_COLLIN_MDB_PATH", "ERA_COLLIN_CODE_LIST_PATH",
            ) if self.environ.get(key)
        }
        compute_payload = {
            "protocol": PROTOCOL, "kind": "COMPUTE", "item": item_payload,
            "operator_environment": operator_environment,
        }
        if self.worker_test_mode:
            compute_payload["test_mode"] = self.worker_test_mode
            compute_payload["test_controls"] = self.worker_test_controls
        raw = self._run_owned_stage(compute_payload, deadline, closure_seconds, supervisor)
        computed = self._decode_worker_response(raw, {"CANDIDATE", "ERROR"})
        if computed["status"] == "ERROR":
            code = computed["reason_code"]
            self.audit.publish(
                "API_ANALYZE_DENIED", {"reason": code, "correlation_id": correlation},
            )
            if code in {"UNSUPPORTED_PROVIDER", "UNSUPPORTED_COUNTY",
                        "EXACTLY_ONE_SELECTOR_REQUIRED", "COLLIN_SOURCE_PATHS_REQUIRED",
                        "COLLIN_SOURCE_PATH_NOT_FOUND", "INVALID_SUPPLEMENTAL_EVIDENCE"}:
                raise ValueError(code)
            raise RuntimeError(code)

        candidate = computed["candidate"]
        candidate_digest = hashlib.sha256(json.dumps(
            candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("ascii")).hexdigest().upper()
        validate_payload = {
            "protocol": PROTOCOL, "kind": "VALIDATE",
            "candidate": computed.get("candidate"),
            "candidate_digest": candidate_digest,
            "selectors": [item.account_id, item.address],
            "source_paths": list(operator_environment.values()),
            "validation_delay_seconds": self.validation_delay_seconds,
        }
        raw = self._run_owned_stage(validate_payload, deadline, closure_seconds, supervisor)
        validated = self._decode_worker_response(raw, {"CANDIDATE", "ERROR"})
        if validated["status"] != "CANDIDATE":
            raise IsolatedExecutionFailure("CANDIDATE_VALIDATION_FAILED")
        candidate = validated["candidate"]
        canonical = json.dumps(
            candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("ascii")
        if candidate_digest != hashlib.sha256(canonical).hexdigest().upper():
            raise IsolatedExecutionFailure("CANDIDATE_VALIDATION_FAILED")
        if self.admission_delay_seconds:
            time.sleep(min(
                self.admission_delay_seconds,
                max(0.0, deadline - time.monotonic()),
            ))
        if time.monotonic() >= deadline or supervisor.cancelled:
            raise IsolatedExecutionTimeout("TIMEOUT")
        if not candidate.get("ok"):
            return self._admit_report(item, correlation, candidate)
        if self.admission_store is None:
            raise IsolatedExecutionFailure("ADMISSION_STORE_REQUIRED")
        response = dict(candidate)
        response["correlation_id"] = correlation
        response_json = json.dumps(response, sort_keys=True, separators=(",", ":"))
        admission_id = hashlib.sha256(
            f"{correlation}:{candidate_digest}".encode("ascii")
        ).hexdigest().upper()
        audit_payload = {
            "correlation_id": correlation, "provider": response["provider"],
            "jurisdiction": response["jurisdiction"], "run_id": response["run_id"],
            "supplemental_evidence_count": len(item.supplemental_evidence or ()),
        }
        intent = AdmissionIntent(
            admission_id, correlation, candidate_digest, response_json,
            "API_ANALYZE_ALLOWED", audit_payload,
        )
        admitted = self.admission_store.admit(
            intent, deadline, time.monotonic,
            lambda: self._authorized_without_audit(authorization),
            lambda: supervisor.cancelled,
        )
        pending = self.admission_store.claim_pending(admission_id)
        if pending is not None:
            self.audit.publish(*pending)
        return response


def create_app(environ=None, operator=execute_operator, audit=None,
               process_boundary_factory=OwnedProcessBoundary,
               worker_test_mode=None, worker_test_controls=None,
               validation_delay_seconds=0, admission_delay_seconds=0,
               admission_store=None):
    service = EraPropertyApiService(
        environ=environ, operator=operator, audit=audit,
        process_boundary_factory=process_boundary_factory,
        worker_test_mode=worker_test_mode,
        worker_test_controls=worker_test_controls,
        validation_delay_seconds=validation_delay_seconds,
        admission_delay_seconds=admission_delay_seconds,
        admission_store=admission_store,
    )
    api = FastAPI(title="ERA Property Analysis API", docs_url=None, redoc_url=None, openapi_url=None)
    api.state.era_service = service

    class DuplicateJsonKey(ValueError):
        pass

    def reject_duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise DuplicateJsonKey("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    @api.exception_handler(RequestValidationError)
    async def validation_error(request, _exc):
        cid = correlation_id(request.headers.get("x-request-id"))
        return error_response("INVALID_REQUEST", cid, 422)

    @api.middleware("http")
    async def request_limit(request: Request, call_next):
        cid = correlation_id(request.headers.get("x-request-id"))
        request.state.correlation_id = cid
        if request.method == "POST" and request.url.path == "/v1/property/analyze":
            request.state.request_supervisor = RequestSupervisor()
            raw_lengths = [
                value for name, value in request.scope.get("headers", ())
                if name.lower() == b"content-length"
            ]
            if not raw_lengths:
                service.audit.publish("API_ANALYZE_DENIED", {"reason": "CONTENT_LENGTH_REQUIRED", "correlation_id": cid})
                return error_response("CONTENT_LENGTH_REQUIRED", cid, 411)
            if len(raw_lengths) != 1:
                service.audit.publish("API_ANALYZE_DENIED", {"reason": "INVALID_CONTENT_LENGTH", "correlation_id": cid})
                return error_response("INVALID_CONTENT_LENGTH", cid, 400)
            try:
                length = raw_lengths[0].decode("ascii")
            except UnicodeDecodeError:
                length = ""
            if not re.fullmatch(r"(?:0|[1-9][0-9]*)", length):
                service.audit.publish("API_ANALYZE_DENIED", {"reason": "INVALID_CONTENT_LENGTH", "correlation_id": cid})
                return error_response("INVALID_CONTENT_LENGTH", cid, 400)
            if int(length) > MAX_REQUEST_BYTES:
                service.audit.publish("API_ANALYZE_DENIED", {"reason": "REQUEST_TOO_LARGE", "correlation_id": cid})
                return error_response("REQUEST_TOO_LARGE", cid, 413)
            chunks = []
            observed = 0
            async for chunk in request.stream():
                observed += len(chunk)
                if observed > MAX_REQUEST_BYTES:
                    service.audit.publish("API_ANALYZE_DENIED", {"reason": "REQUEST_TOO_LARGE", "correlation_id": cid})
                    return error_response("REQUEST_TOO_LARGE", cid, 413)
                chunks.append(chunk)
            raw_body = b"".join(chunks)
            request._body = raw_body
            try:
                json.loads(raw_body.decode("utf-8"), object_pairs_hook=reject_duplicate_keys)
            except DuplicateJsonKey:
                service.audit.publish("API_ANALYZE_DENIED", {"reason": "DUPLICATE_JSON_KEY", "correlation_id": cid})
                return error_response("INVALID_REQUEST", cid, 422)
            except (UnicodeDecodeError, json.JSONDecodeError):
                service.audit.publish("API_ANALYZE_DENIED", {"reason": "INVALID_JSON", "correlation_id": cid})
                return error_response("INVALID_REQUEST", cid, 422)
        try:
            return await call_next(request)
        except asyncio.CancelledError:
            supervisor = getattr(request.state, "request_supervisor", None)
            if supervisor is not None:
                quiescence = float(service.environ.get(
                    "ERA_API_QUIESCENCE_SECONDS", DEFAULT_QUIESCENCE_SECONDS,
                ))
                await asyncio.to_thread(supervisor.cancel, quiescence)
                await asyncio.to_thread(supervisor.wait_closed, quiescence)
            raise

    @api.get("/healthz")
    async def healthz():
        return service.health()

    @api.post("/v1/property/analyze")
    async def analyze(request: Request, item: AnalyzeRequest, authorization: str | None = Header(default=None)):
        cid = request.state.correlation_id
        try:
            timeout = float(service.environ.get("ERA_API_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
            quiescence = float(service.environ.get(
                "ERA_API_QUIESCENCE_SECONDS", DEFAULT_QUIESCENCE_SECONDS,
            ))
            if (not (0 < timeout <= 300)
                    or not (MIN_QUIESCENCE_SECONDS <= quiescence <= MAX_QUIESCENCE_SECONDS)):
                raise ValueError("INVALID_TIMEOUT_CONFIGURATION")
            supervisor = request.state.request_supervisor
            task = asyncio.create_task(asyncio.to_thread(
                service.analyze_isolated,
                item, authorization, cid, timeout, quiescence, supervisor,
            ))
            try:
                return await task
            except asyncio.CancelledError:
                await asyncio.to_thread(supervisor.cancel, quiescence)
                await asyncio.to_thread(supervisor.wait_closed, quiescence)
                raise
        except (OperationCancelled, IsolatedExecutionTimeout, AdmissionExpired, AdmissionCancelled):
            service.audit.publish("API_ANALYZE_DENIED", {"reason": "TIMEOUT", "correlation_id": cid})
            return error_response("TIMEOUT", cid, 504)
        except IsolatedExecutionFailure:
            service.audit.publish("API_ANALYZE_DENIED", {
                "reason": "ISOLATED_EXECUTION_FAILED", "correlation_id": cid,
            })
            return error_response("ISOLATED_EXECUTION_FAILED", cid, 500, "Internal failure")
        except PermissionError as exc:
            return error_response(str(exc), cid, 401, "Authentication failed")
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
