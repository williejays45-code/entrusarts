# ERA Windows Private Beta — Phase B execution contract

Phase B remains **NO-GO**. This contract defines installation gates; it does not authorize or perform them.

## Supported host and identity

The beta host must be a supported Windows Pro, Enterprise, or Server edition with Task Scheduler,
local security-policy administration, Microsoft Jet/OLE DB compatibility, and Windows PowerShell 5.1.
Windows Home is not supported. `EnTrusERAService` must be a dedicated local, non-administrator identity.
It receives only **Log on as a batch job** and is explicitly denied local and Remote Desktop interactive
logon. A disposable-host test must prove that batch logon still works after both denials.

The account password must be generated randomly through an approved secret manager, never printed or
placed in a script. The installation operator enters it only into the protected Task Scheduler credential
prompt/API. Its owner, escrow/recovery policy, expiry setting, rotation interval, and task-credential update
procedure must be recorded before installation. A password rotation is incomplete until the task runs
successfully with the replacement and the previous password is rejected.

## Task Scheduler and DPAPI

The task uses **Password** logon (`TASK_LOGON_PASSWORD`), loads the service identity’s user profile, starts
only the supervisor, uses `IgnoreNew`, and delegates Uvicorn recovery exclusively to the supervisor. S4U,
interactive-token, group, and SYSTEM logon types are prohibited for this beta.

The dedicated account SID is recorded as `serviceIdentitySid` in the administrator-restricted configuration.
The Scheduled Task Run identity must resolve to that exact SID, and operational `Run` refuses any mismatch.
The machine-wide mutex owner must be that pinned service SID during scheduled operation. Both owner and DACL are
validated; an existing object with any other owner or allowed principal is rejected, never repaired or adopted.

The bearer token is generated with a cryptographic RNG in a non-recording secure console under the service
identity. That same identity exports a `PSCredential` or `SecureString` with `Export-Clixml`, producing
user-scope DPAPI protection. No `-AsPlainText`, command argument, transcript, history, ordinary environment
registry, task XML, clipboard workflow, or plaintext temporary file is permitted. Installation must test
`Import-Clixml` and API authentication from the scheduled identity with its profile loaded.

The approved client stores its one necessary token copy only in the organization’s approved credential
manager. Rotation is: generate replacement, replace DPAPI file atomically under the service identity,
restart the supervisor, prove the new token works, prove the previous token fails, then revoke and dispose
of the old client entry. Recovery requires generating a new token; plaintext server-side recovery is not
supported.

## ACL and integrity matrix

All paths use protected inheritance and explicit grants. Administrators and SYSTEM retain full control.
The service identity receives: read/execute on signed source and virtual environment; read on configuration,
credential, certified MDB/XLS, and signed hash authority; modify only on state and log directories. Routine
operators receive read on redacted operator logs only. Only administrators receive diagnostic-log access.
No other principal receives access. Effective Access and an attempted service-identity write must prove the
MDB/XLS and authority record are read-only.

Certified inputs are copied only from the established files after source and destination SHA-256 comparison.
The copy record contains original path identity, size, hash, UTC, release identity, and operator identity but
no record contents. The restricted or signed hash record is the accepted drift authority; copying data does
not create independent tamper-proof authority, and administrators/owners remain trusted.

## Script integrity

Before installation, select an existing organization-trusted code-signing certificate with private-key use
restricted to authorized release operators. Sign every executed PowerShell source, verify signature status and
chain under the service identity, and record signer thumbprint in the release record. If no trusted signing
authority exists, installation fails closed. Machine-wide execution policy must not be weakened.

## Install, repair, rotation, and rollback

Every operation first inventories current ownership and either converges an ERA-owned object to the declared
state or refuses an unexpected object. Re-running install or repair must not duplicate accounts, rights, ACL
entries, directories, credentials, tasks, or recovery actions. Replacement files use atomic rename and retain
a recoverable prior signed version until verification succeeds.

Rollback order is mandatory: disable new task starts; invoke the nonce-bound two-phase cooperative stop, which
prevalidates the complete set, writes intent, receives a nonce-bound ready acknowledgement, atomically commits,
then stops the exact child handle and exits the supervisor (a valid commit remains authoritative after client
disconnect; before commit timeout or failure terminates nothing and restores recovery);
remove the task; remove only ERA-added user rights; remove only ERA-added ACL grants; revoke/remove the
DPAPI credential; retain redacted operator logs and administrator-restricted diagnostics per retention policy;
optionally disable, then remove, the service account only after ownership review. Each step is idempotent and
records a privacy-safe result. Failure stops the sequence and reports the last completed step; it never broadens
permissions or deletes diagnostics to hide failure.

The stop handshake timeout is explicitly bounded to 10–300 seconds inclusive in every control mode. Full
operational configuration must additionally set it above the health interval plus four seconds; malformed,
below-minimum, or above-maximum values fail closed before any stop intent is written.

## Disposable-host acceptance gate

Before any real beta host, a disposable supported Windows host must prove DPAPI create/decrypt under scheduled
identity, profile loading, exact rights, effective ACLs, signature enforcement, cross-session duplicate-start
rejection, abandoned-lock recovery, stale-PID and nonce refusal, emergency stop with broken startup inputs,
surviving-child reconciliation, forced child restart, operator-log rotation without request interruption,
diagnostic cooldown and separate budget, bounded retention, token replacement/old-token rejection, ordered
rollback, and repeat install/repair/uninstall. Tests use fabricated sources and identifiers only.

Production-verifier exit code `2` is **UNPROVEN/non-success**, not PASS. CI, task wrappers, and release gates must
accept only exit code `0`; they must preserve exit code `2` as an explicit blocking result.
