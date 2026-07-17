# LIVE DATA LAW

**Status:** permanent standing rule, adopted before LIVE-ADAPTER-001.
**Scope:** every live provider adapter, present and future, without exception.

## The Law

No live provider adapter may:

1. **Bypass the transport layer** — all outbound requests go through `era.network.network_client.NetworkClient`, wrapping an `HttpTransport`. No connector opens a socket, calls `urllib`/`requests` directly, or otherwise reaches the network outside this layer.
2. **Bypass rate limiting** — every request against a connector goes through `era.acquisition.rate_limiter.RateLimiter.check_and_record()` before it is sent. No adapter maintains its own request counter or its own notion of "is this okay to send."
3. **Bypass retry enforcement** — every request goes through `era.acquisition.retry_executor.RetryExecutor.run()`. No adapter implements its own retry loop, its own backoff, or its own transient/permanent failure classification.
4. **Bypass provenance creation** — every field a live adapter returns flows through ECM (canonicalization) and EPM (`EvidenceProvenanceManager.register_evidence()`) before it is usable anywhere else in the system. No adapter writes directly to UPR, DEC, POL, or EXP.
5. **Bypass policy validation** — no adapter or connector decides for itself whether evidence is sufficient, whether a decision is acceptable, or whether an export is authorized. Those calls belong to DEC and POL alone, exactly as C2 already established for the recommendation engine's confidence boundary — this is the same boundary, applied to live data.
6. **Bypass audit logging** — every stage a live request passes through publishes to its own `BaseAuditPublisher`, exactly as every existing engine already does. No adapter suppresses, filters, or routes around its own audit trail.
7. **Bypass transaction boundaries** — a live-sourced `run_property()` call is subject to the exact same TXN-001 transaction as a stub-sourced one. No adapter's writes commit outside that boundary, and no adapter's failure is exempt from the same rollback every other stage failure already gets.

**Every live record entering ERA must traverse the complete verified pipeline** — JRE → SRR → RATE_LIMIT → LPA → ECM → EPM → MSF → ECR → UPR → DEC → POL → EXP — with no shortcut, no side door, and no adapter-specific exception to any of the seven rules above.

## Why this is enforceable, not just stated

Every rule above names the actual class and method that enforces it, all of which already exist and are already regression-tested (47/47 as of this writing):

| Rule | Enforced by | Verified by |
|---|---|---|
| Transport layer | `NetworkClient` / `HttpTransport` | `verify_network001.py` |
| Rate limiting | `RateLimiter.check_and_record()` | `verify_rate_retry001.py` |
| Retry enforcement | `RetryExecutor.run()` | `verify_rate_retry001.py`, `verify_network001.py` |
| Provenance creation | `CanonicalEvidenceModel`, `EvidenceProvenanceManager` | `verify_ecm001.py`, `verify_epm001_persistence.py` |
| Policy validation | `DecisionEngine`, `PolicyEngine` | `verify_dec001.py`, `verify_pol001.py` |
| Audit logging | `BaseAuditPublisher` (all engines) | `verify_audit_persistence.py` |
| Transaction boundaries | `Pipeline.run_property()` / `Transaction` | `verify_txn001.py` |

A future live adapter that violates any rule above should fail one of these existing tests, or a new test built against this table — not require a new enforcement mechanism to be invented after the fact.

## First live adapter scope (per FORGE, agreed)

When LIVE-ADAPTER-001 begins:

- **One provider only.**
- **One endpoint or one official data source only.**
- **Read-only. No scraping. No write capability.**
- **Full audit trail.**
- **Full rollback on failure.**
- **Full regression after integration.**

This scope is deliberately narrow so the first live integration is a controlled test of whether the infrastructure built through NETWORK-001 actually holds up against real-world response behavior (timing, malformed data, unexpected status codes) — not an expansion of what the system does. Widening scope is a decision for after LIVE-ADAPTER-001 is verified, not before.
