# ERA Windows Private Beta — Phase A.1-R2

This package prepares, but does not install, a Windows-hosted private beta. It does not create a
service account, write a credential, modify ACLs, register a Scheduled Task, install dependencies,
or expose ERA beyond loopback.

Phase A.1-R2 adds a configuration-pinned service SID, secured machine-wide ownership with owner validation,
production process fingerprints, nonce-bound two-phase cooperative stop, complete stale-run validation,
exact process-handle cleanup, and bounded logging
that does not use the crash-recovery budget for routine rotation. The detailed, still
non-executable Phase B requirements are in `PHASE_B_CONTRACT.md`.

## Security and authority boundaries

- A secured `Global\EnTrus.ERA.PrivateBeta.Supervisor` mutex is the machine-wide ownership authority.
  `serviceIdentitySid` is pinned in the administrator-restricted deployment configuration, and `Run` fails
  unless the current identity exactly matches it. Its owner and ACL are restricted to that pinned service identity,
  SYSTEM, and Administrators; failure to
  establish or verify both fails closed, and an unexpected pre-created object is never adopted or repaired.
  An abandoned mutex is explicitly acquired and recorded. The supervisor is the sole Uvicorn recovery authority. Task Scheduler starts the supervisor and
  may restart it only after supervisor-level failure.
- The Uvicorn child command is `python -B -m uvicorn era.api:app --host 127.0.0.1 --port 8081`
  plus logging-suppression arguments. It is never exposed publicly by this package.
- The bearer token is loaded from a DPAPI-bound CLIXML credential created outside Git under the
  eventual service identity. It is inherited by the child through its process environment and is
  never placed in a task action, XML, command line, config file, or persistent environment variable.
- Expected source hashes in the restricted deployment config provide fail-closed drift detection.
  They are not independent tamper-proof authority. Phase B must restrict that config or bind it to a
  signed release record.
- Routine operator logs contain structured lifecycle events only. Raw stdout, stderr, and Python
  tracebacks go to a separate diagnostic directory which Phase B must restrict to administrators.
- Stop reads only the control-state location. It prevalidates the complete supervisor/child set and writes an
  atomic nonce-bound intent. The supervisor revalidates the process set and writes a nonce-bound `READY`
  acknowledgement. Only then does the client atomically write `COMMIT`; that commit authorizes the supervisor to
  stop its exact child handle and exit even if the client subsequently disconnects. Before commit, invalid, stale,
  replayed, partial, failed, or timed-out requests terminate nothing and normal recovery is restored.
  `stopHandshakeSeconds` is valid only from 10 through 300 seconds (inclusive), including control-only
  `Stop`/`Restart`; a full operational configuration must also exceed `healthIntervalSeconds + 4`.
- Operator logs rotate without restarting Uvicorn. Each child receives unique diagnostic files. Diagnostic size
  restarts use a separate budget and cooldown, never consume the crash budget, and enforce a hard fail-closed cap.
- Token rotation means replacing the DPAPI credential under the service identity and restarting the
  supervisor. Phase B must verify the old token is rejected after restart.

## Package verification

Copy `config.example.json` to a location outside Git and replace every placeholder. Preflight is
fail-closed for missing sources, wrong hashes, non-loopback binding, missing Python, or missing ERA
source. `-VerificationOnly` permits only the credential file to be absent; it does not weaken source
or hash validation.

```powershell
powershell -NoProfile -File .\ops\windows_private_beta\verify-phase-a.ps1
powershell -NoProfile -File .\ops\windows_private_beta\verify-phase-a1.ps1
powershell -NoProfile -File .\ops\windows_private_beta\verify-phase-a1-production.ps1
powershell -NoProfile -File .\ops\windows_private_beta\era-supervisor.ps1 `
  -Mode Preflight -VerificationOnly -ConfigPath C:\restricted\era-host.json
powershell -NoProfile -File .\ops\windows_private_beta\era-supervisor.ps1 `
  -Mode TaskPreview -ConfigPath C:\restricted\era-host.json
```

The host gate is deliberately separate from `python -B -m era.verify_all`; host-specific PowerShell
operations are not part of the cross-platform reasoning gate.

The host verifier also checks the exception boundary: child stderr is routed only to the diagnostic
channel, while operator events contain fixed lifecycle codes rather than exception text or paths.

Verifier exit codes are part of the gate: `0` means every executed check passed, `1` means a failure, and
`2` means **UNPROVEN/non-success**. CI and release automation must never translate exit code `2` into PASS.

## Phase B installation gates

Before private-beta operation, an administrator must satisfy `PHASE_B_CONTRACT.md` and separately prove:

1. The dedicated account exists and owns the DPAPI credential.
2. Source code, certified MDB/XLS files, configuration, and credential ACLs are least-privilege;
   the account cannot modify the certified inputs.
3. The diagnostic log directory is administrator-only and exception paths do not enter operator logs.
4. The supervisor script is signed or allowed by the organization’s controlled script policy.
5. The Scheduled Task action matches `TaskPreview`, contains no secrets, and has one-instance policy.
6. Supervisor-level recovery works without creating duplicate Uvicorn processes.
7. Credential rotation followed by restart rejects the previous bearer token.

None of these installation gates is claimed by Phase A.
