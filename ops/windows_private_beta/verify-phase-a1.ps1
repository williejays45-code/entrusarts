[CmdletBinding()]param()
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'phase-a1-core.ps1')
$checks=[ordered]@{};$root=Join-Path ([IO.Path]::GetTempPath()) ('era-phase-a1-r2-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root|Out-Null;$processes=New-Object Collections.Generic.List[Diagnostics.Process]
try{
    $supervisorText=Get-Content -Raw (Join-Path $PSScriptRoot 'era-supervisor.ps1')
    $coreText=Get-Content -Raw (Join-Path $PSScriptRoot 'phase-a1-core.ps1')
    $contractText=Get-Content -Raw (Join-Path $PSScriptRoot 'PHASE_B_CONTRACT.md')

    $checks.machine_wide_lock_design=$supervisorText -match "New-SecureGlobalMutex 'Global\\" -and $coreText -match 'MutexSecurity'
    $identity=[Security.Principal.WindowsIdentity]::GetCurrent();$serviceSid=$identity.User.Value
    $trusted=@($serviceSid,'S-1-5-18','S-1-5-32-544')
    $security=New-Object Security.AccessControl.MutexSecurity;$allow=[Security.AccessControl.AccessControlType]::Allow
    foreach($sidText in $trusted){$sid=New-Object Security.Principal.SecurityIdentifier($sidText)
        $security.AddAccessRule((New-Object Security.AccessControl.MutexAccessRule($sid,[Security.AccessControl.MutexRights]::FullControl,$allow)))}
    $security.SetOwner($identity.User)
    $checks.trusted_mutex_owner_and_dacl=Test-MutexSecurityAuthority $security $trusted
    $security.SetOwner((New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')))
    $checks.non_service_trusted_owner_refused=-not(Test-MutexSecurityAuthority $security $trusted $serviceSid)
    $security.SetOwner((New-Object Security.Principal.SecurityIdentifier('S-1-1-0')))
    $checks.hostile_precreated_owner_refused=-not(Test-MutexSecurityAuthority $security $trusted)

    $lockName='Global\EnTrus.ERA.R2.Duplicate.'+[Guid]::NewGuid().ToString('N');$lock=New-SecureGlobalMutex $lockName $serviceSid
    try{$script=Join-Path $root 'duplicate.ps1';$duplicateContent=@'
param($Core,$Name,$Sid)
. $Core
try{$held=New-SecureGlobalMutex $Name $Sid;Exit-SecureGlobalMutex $held;exit 0}catch{if($_.Exception.Message -eq 'SUPERVISOR_ALREADY_RUNNING'){exit 23};exit 24}
'@
        $duplicateContent|Set-Content $script
        $duplicate=Start-Process powershell.exe -ArgumentList @('-NoProfile','-File',$script,(Join-Path $PSScriptRoot 'phase-a1-core.ps1'),$lockName,$serviceSid) -Wait -PassThru -WindowStyle Hidden
        $checks.duplicate_start_rejected=$duplicate.ExitCode -eq 23}finally{Exit-SecureGlobalMutex $lock}

    $abandonedName='Global\EnTrus.ERA.R2.Abandoned.'+[Guid]::NewGuid().ToString('N');$keeper=New-SecureGlobalMutex $abandonedName $serviceSid
    $keeper.Mutex.ReleaseMutex();$script=Join-Path $root 'abandon.ps1';$abandonContent=@'
param($Core,$Name,$Sid)
. $Core
$held=New-SecureGlobalMutex $Name $Sid
exit 0
'@
    $abandonContent|Set-Content $script
    $abandoner=Start-Process powershell.exe -ArgumentList @('-NoProfile','-File',$script,(Join-Path $PSScriptRoot 'phase-a1-core.ps1'),$abandonedName,$serviceSid) -Wait -PassThru -WindowStyle Hidden
    $abandoned=$false;try{$null=$keeper.Mutex.WaitOne(0,$false)}catch [Threading.AbandonedMutexException]{$abandoned=$true}
    try{$checks.windows_abandoned_mutex_semantics=$abandoner.ExitCode -eq 0 -and $abandoned}finally{try{$keeper.Mutex.ReleaseMutex()}catch{};$keeper.Mutex.Dispose()}

    function New-FakeFingerprint([int]$Id,[int]$Parent,[long]$Ticks,[string]$Command){[ordered]@{
        pid=$Id;parentPid=$Parent;creationUtcTicks=$Ticks;executablePath='C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe';commandLine=$Command}}
    $sup=New-FakeFingerprint 100 1 1000 'powershell era-supervisor.ps1';$child=New-FakeFingerprint 101 100 1001 'python uvicorn era.api:app'
    $checks.complete_process_set_accepts_exact=Test-CompleteProcessSet $sup $sup $child $child
    $badSup=[ordered]@{}+$sup;$badSup.creationUtcTicks=999
    $checks.invalid_supervisor_refused_before_termination=-not(Test-CompleteProcessSet $sup $badSup $child $child)
    $badChild=[ordered]@{}+$child;$badChild.parentPid=999
    $checks.invalid_child_refused_before_termination=-not(Test-CompleteProcessSet $sup $sup $child $badChild)
    $checks.partial_process_state_refused=-not(Test-CompleteProcessSet $sup $sup $null $child)

    $stale=[pscustomobject]@{schemaVersion=2;phase='RUNNING';runNonce=('a'*64);supervisor=$sup;child=$child}
    $checks.complete_stale_record_accepted=Test-StaleRunRecord $stale
    foreach($mutation in @(
        @{Name='stale_schema_refused';Field='schemaVersion';Value=1},
        @{Name='stale_phase_refused';Field='phase';Value='READY'},
        @{Name='stale_nonce_refused';Field='runNonce';Value='bad'})){
        $candidate=[pscustomobject]@{schemaVersion=$stale.schemaVersion;phase=$stale.phase;runNonce=$stale.runNonce;supervisor=$sup;child=$child}
        $candidate.($mutation.Field)=$mutation.Value;$checks[$mutation.Name]=-not(Test-StaleRunRecord $candidate)
    }
    $badStaleSupervisor=[ordered]@{}+$sup;$badStaleSupervisor.commandLine='powershell unrelated.ps1'
    $checks.stale_supervisor_command_refused=-not(Test-StaleRunRecord ([pscustomobject]@{schemaVersion=2;phase='RUNNING';runNonce=('a'*64);supervisor=$badStaleSupervisor;child=$child}))
    $badStaleChild=[ordered]@{}+$child;$badStaleChild.parentPid=999
    $checks.stale_child_parent_refused=-not(Test-StaleRunRecord ([pscustomobject]@{schemaVersion=2;phase='RUNNING';runNonce=('a'*64);supervisor=$sup;child=$badStaleChild}))

    $checks.handshake_minimum_accepted=(Get-ValidatedHandshakeSeconds 10) -eq 10
    $checks.handshake_maximum_accepted=(Get-ValidatedHandshakeSeconds 300) -eq 300
    foreach($invalid in @(9,301,'invalid')){$refused=$false;try{$null=Get-ValidatedHandshakeSeconds $invalid}catch{$refused=$_.Exception.Message -eq 'INVALID_STOP_HANDSHAKE_SECONDS'}
        $checks["handshake_$($invalid)_refused"]=$refused}
    $supervisorPath=Join-Path $PSScriptRoot 'era-supervisor.ps1'
    foreach($case in @(@{Name='control_minimum';Value=10;Expected=0},@{Name='control_maximum';Value=300;Expected=0},
            @{Name='control_below_minimum';Value=9;Expected=1},@{Name='control_above_maximum';Value=301;Expected=1})){
        $controlConfig=Join-Path $root "$($case.Name).json"
        @{stateDirectory=$root;stopHandshakeSeconds=$case.Value}|ConvertTo-Json|Set-Content -LiteralPath $controlConfig
        $controlProbe=Start-Process powershell.exe -ArgumentList @('-NoProfile','-File',$supervisorPath,'-Mode','TaskPreview','-ConfigPath',$controlConfig) `
            -Wait -PassThru -WindowStyle Hidden
        $checks["$($case.Name)_enforced"]=$controlProbe.ExitCode -eq $case.Expected
    }

    $checks.no_mock_in_operational_termination=$coreText -notmatch 'FingerprintResolver|scriptblock\]\$Fingerprint' -and
        $supervisorText -notmatch 'FingerprintResolver|MockFingerprint|VerificationOnly.*Fingerprint'
    $checks.no_raw_pid_termination=$supervisorText -notmatch 'Stop-Process\s+-Id' -and $coreText -notmatch 'Stop-Process\s+-Id'
    $checks.pinned_service_identity=$supervisorText -match "'serviceIdentitySid'" -and
        $supervisorText -match 'New-SecureGlobalMutex ''Global\\EnTrus.ERA.PrivateBeta.Supervisor'' \(\[string\]\$config.serviceIdentitySid\)' -and
        $coreText -match 'SERVICE_IDENTITY_MISMATCH' -and
        $supervisorText.IndexOf("throw 'SERVICE_IDENTITY_MISMATCH'") -lt $supervisorText.IndexOf('Invoke-Preflight $config')
    $checks.cim_precedes_child_start=$supervisorText.IndexOf('Get-ProcessFingerprint $PID') -lt $supervisorText.IndexOf("Start-Process -FilePath `$config.pythonExe")
    $checks.exact_handle_cleanup=$supervisorText -match 'catch\{Stop-ExactProcessHandle \$child' -and $coreText -match '\$Process\.Kill\(\)'

    $statePath=Join-Path $root 'state.json';$noncePath=Join-Path $root 'nonce';$intentPath=Join-Path $root 'intent.json';$ackPath=Join-Path $root 'ack.json';$commitPath=Join-Path $root 'commit.json'
    Set-Content $noncePath ('a'*64) -NoNewline;Write-AtomicJson $statePath ([ordered]@{runNonce=('a'*64);supervisor=$sup;child=$child})
    $paths=[pscustomobject]@{State=$statePath;Nonce=$noncePath;Intent=$intentPath;Ack=$ackPath;Commit=$commitPath}
    Write-AtomicJson $intentPath ([ordered]@{runNonce=('b'*64);requestNonce=('c'*64);expiresUtc=[DateTime]::UtcNow.AddMinutes(1).ToString('o')})
    $checks.nonce_bound_stop_intent=$supervisorText -match 'intent.runNonce -ne \$State.runNonce' -and
        $supervisorText -match "requestNonce -notmatch '\^\[a-f0-9\]\{64\}\$'"
    Write-AtomicJson $ackPath ([ordered]@{status='READY'})
    $checks.replayed_stop_refused=$supervisorText -match 'STOP_INTENT_REPLAY' -and $supervisorText -match 'STOP_REQUEST_ACTIVE_OR_REPLAYED'
    Remove-Item $ackPath;Write-AtomicJson $intentPath ([ordered]@{runNonce=('a'*64);requestNonce=('c'*64);expiresUtc=[DateTime]::UtcNow.AddMinutes(-1).ToString('o')})
    $checks.stale_stop_refused=$supervisorText -match 'STOP_INTENT_INVALID_OR_STALE'
    $runNonceForCommit='a'*64;$requestNonceForCommit='b'*64;$readyNonceForCommit='c'*64
    $validCommit=[pscustomobject]@{status='COMMIT';runNonce=$runNonceForCommit;requestNonce=$requestNonceForCommit;readyNonce=$readyNonceForCommit;utc=[DateTime]::UtcNow.ToString('o')}
    $checks.valid_commit_accepted=Test-StopCommitRecord $validCommit $runNonceForCommit $requestNonceForCommit $readyNonceForCommit ([DateTime]::UtcNow.AddMinutes(1))
    $checks.commit_nonce_mismatch_refused=-not(Test-StopCommitRecord $validCommit $runNonceForCommit $requestNonceForCommit ('d'*64) ([DateTime]::UtcNow.AddMinutes(1)))
    $checks.expired_commit_refused=-not(Test-StopCommitRecord $validCommit $runNonceForCommit $requestNonceForCommit $readyNonceForCommit ([DateTime]::UtcNow.AddSeconds(-1)))
    $cooperativeStart=$supervisorText.IndexOf('function Invoke-CooperativeStop')
    $cooperativeEnd=$supervisorText.IndexOf('function Resolve-PriorRun',$cooperativeStart)
    $cooperativeText=$supervisorText.Substring($cooperativeStart,$cooperativeEnd-$cooperativeStart)
    $checks.stop_timeout_fails_without_forced_kill=$cooperativeText -match 'STOP_ACK_TIMEOUT_OR_MISMATCH' -and
        $cooperativeText -notmatch 'Stop-ExactProcessHandle'
    $stopRequestedPosition=$supervisorText.IndexOf('$stopRequested=$true');$ackPosition=$supervisorText.IndexOf('Write-AtomicJson $Paths.Ack')
    $stopChildPosition=$supervisorText.IndexOf('Stop-ExactProcessHandle $child',$stopRequestedPosition)
    $commitPosition=$supervisorText.IndexOf('Test-StopCommitRecord',$ackPosition)
    $checks.two_phase_commit_precedes_child_stop=$ackPosition -ge 0 -and $ackPosition -lt $commitPosition -and
        $commitPosition -lt $stopRequestedPosition -and $stopRequestedPosition -lt $stopChildPosition
    $checks.stop_validation_failure_does_not_kill=$supervisorText -match 'catch\{try\{Write-OperatorEvent \$operatorLog ''STOP_REQUEST_REJECTED''' -and
        $supervisorText -notmatch 'STOP_REQUEST_REJECTED[^\r\n]*Stop-Exact'
    $checks.precommit_failure_restores_recovery=$supervisorText -match 'Remove-Item -LiteralPath \$Paths.Intent,\$Paths.Ack,\$Paths.Commit' -and
        $supervisorText -match 'Write-AtomicJson \$Paths.State \$State' -and $supervisorText -match 'if\(Invoke-SupervisorStopHandshake' -and
        $supervisorText -match 'if\(\$authorized\)\{return \$true\}'
    $checks.restart_race_suppressed=$supervisorText -match 'while\(-not \$stopRequested\)' -and $checks.two_phase_commit_precedes_child_stop

    $checks.abandoned_or_stale_state_reconciled=$supervisorText -match 'Resolve-PriorRun \$paths' -and
        $supervisorText -match 'PRIOR_RUN_RECONCILIATION_UNPROVEN' -and $supervisorText -match 'Stop-ExactProcessHandle \$recovered.Handle'

    $operator=Join-Path $root 'operator.log';[IO.File]::WriteAllText($operator,('o'*2048))
    $availabilityProbe=Start-Process powershell.exe -ArgumentList @('-NoProfile','-Command','Start-Sleep -Seconds 30') -PassThru -WindowStyle Hidden
    $processes.Add($availabilityProbe);Rotate-ClosedLog $operator 1024 2
    $checks.operator_rotation_preserves_availability=(Test-Path "$operator.1") -and -not $availabilityProbe.HasExited
    $diagnostic=Join-Path $root 'era-diagnostic-test.log';[IO.File]::WriteAllText($diagnostic,'d')
    Remove-ExpiredDiagnosticLogs $root 1
    $checks.unique_diagnostic_streams=$supervisorText -match 'era-diagnostic-\$runNonce-\$sequence' -and
        $supervisorText -notmatch 'Rotate-ClosedLog \$stdoutLog'
    $checks.rotation_budget_separate=$supervisorText -match '\$crashTimes=' -and $supervisorText -match '\$diagnosticTimes=' -and
        $supervisorText -match 'diagnosticRestartCooldownSeconds'
    $times=New-Object Collections.Generic.List[DateTime];$policyNow=[DateTime]::UtcNow
    $checks.diagnostic_restart_policy_allow=(Get-DiagnosticRestartDecision $times $policyNow 300 60 2) -eq 'ALLOW'
    $times.Add($policyNow);$checks.diagnostic_restart_policy_cooldown=(Get-DiagnosticRestartDecision $times $policyNow.AddSeconds(10) 300 60 2) -eq 'DEFER'
    $times.Add($policyNow.AddSeconds(70));$checks.diagnostic_restart_policy_separate_budget=(Get-DiagnosticRestartDecision $times $policyNow.AddSeconds(80) 300 60 2) -eq 'EXHAUSTED' -and
        $supervisorText -match 'DIAGNOSTIC_HARD_LIMIT_REACHED'
    $checks.contract_covers_all_findings=$contractText -match 'mutex owner' -and $contractText -match 'TASK_LOGON_PASSWORD' -and
        $contractText -match 'previous token fails' -and $contractText -match 'Machine-wide execution policy must not be weakened' -and
        $contractText -match 'Each step is idempotent' -and $contractText -match 'stale-PID and nonce refusal'
    $rollbackTerms=@('disable new task starts','nonce-bound two-phase cooperative stop','remove the task','remove only ERA-added user rights',
        'remove only ERA-added ACL grants','DPAPI credential','retain redacted operator logs')
    $rollbackPositions=@($rollbackTerms|ForEach-Object{$contractText.IndexOf($_,[StringComparison]::OrdinalIgnoreCase)})
    $rollbackOrdered=$true;for($index=0;$index -lt $rollbackPositions.Count;$index++){
        if($rollbackPositions[$index] -lt 0 -or ($index -gt 0 -and $rollbackPositions[$index] -le $rollbackPositions[$index-1])){$rollbackOrdered=$false}}
    $checks.rollback_order_and_idempotence=$rollbackOrdered -and $contractText -match 'Each step is idempotent'
    $readmeText=Get-Content -Raw (Join-Path $PSScriptRoot 'README.md')
    $productionText=Get-Content -Raw (Join-Path $PSScriptRoot 'verify-phase-a1-production.ps1')
    $checks.exit_two_documented_unproven=$readmeText -match 'UNPROVEN/non-success' -and $readmeText -match 'never translate exit code `2` into PASS' -and
        $productionText -match '2=UNPROVEN/non-success' -and $productionText -match 'if\(\$unproven.Count\)\{exit 2\}'
}finally{
    foreach($process in $processes){if($process -and -not $process.HasExited){$process.Kill();$process.WaitForExit()}}
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
$failed=0;foreach($entry in $checks.GetEnumerator()){$result=if($entry.Value){'PASS'}else{'FAIL';$failed++};Write-Output "$($entry.Key): $result"}
Write-Output "WINDOWS PRIVATE BETA PHASE A.1-R2: $($checks.Count-$failed)/$($checks.Count) PASS";if($failed){exit 1}
