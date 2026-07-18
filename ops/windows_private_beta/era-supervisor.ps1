[CmdletBinding()]
param(
    [ValidateSet('Run','Preflight','Stop','Restart','TaskPreview')][string]$Mode='Run',
    [Parameter(Mandatory=$true)][string]$ConfigPath,
    [switch]$VerificationOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'phase-a1-core.ps1')

function Read-Config([string]$Path,[switch]$ControlOnly) {
    $resolved=(Resolve-Path -LiteralPath $Path).Path
    $value=Get-Content -Raw -LiteralPath $resolved | ConvertFrom-Json
    $required=if($ControlOnly){@('stateDirectory')}else{@('sourceRoot','pythonExe','credentialFile','collinMdbPath',
        'collinMdbSha256','collinCodeListPath','collinCodeListSha256','stateDirectory','operatorLogDirectory','serviceIdentitySid',
        'diagnosticLogDirectory','host','port','serviceVersion','healthStartupSeconds','healthIntervalSeconds',
        'maxChildRestarts','restartWindowSeconds','stopHandshakeSeconds','maxDiagnosticRestarts',
        'diagnosticRestartCooldownSeconds','maxLogBytes','logRetentionCount')}
    foreach($name in $required){if(-not $value.PSObject.Properties[$name] -or
            [string]::IsNullOrWhiteSpace([string]$value.$name)){throw "CONFIG_MISSING_FIELD:$name"}}
    $handshake=Get-ValidatedHandshakeSeconds $(if($value.PSObject.Properties['stopHandshakeSeconds']){$value.stopHandshakeSeconds}else{$null})
    if(-not $ControlOnly){
        if([string]$value.serviceIdentitySid -notmatch '^S-1-5-21-(?:[0-9]+-){3}[0-9]+$'){throw 'SERVICE_IDENTITY_SID_INVALID'}
        if($value.host -ne '127.0.0.1'){throw 'LOOPBACK_BINDING_REQUIRED'}
        if([int]$value.port -lt 1024 -or [int]$value.port -gt 65535){throw 'INVALID_PORT'}
        if([int]$value.healthStartupSeconds -lt 1 -or [int]$value.healthIntervalSeconds -lt 1 -or
            [int]$value.maxChildRestarts -lt 1 -or [int]$value.restartWindowSeconds -lt 1 -or
            $handshake -le ([int]$value.healthIntervalSeconds+4) -or
            [int]$value.maxDiagnosticRestarts -lt 1 -or [int]$value.diagnosticRestartCooldownSeconds -lt 1 -or
            [long]$value.maxLogBytes -lt 1024 -or [int]$value.logRetentionCount -lt 1){throw 'INVALID_OPERATIONAL_LIMIT'}
    }
    return $value
}

function Assert-FileHash([string]$Path,[string]$Expected,[string]$Label){
    if(-not(Test-Path -LiteralPath $Path -PathType Leaf)){throw "${Label}_MISSING"}
    $actual=(Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash
    if(-not[string]::Equals($actual,$Expected,[StringComparison]::OrdinalIgnoreCase)){throw "${Label}_HASH_MISMATCH"}
}

function Invoke-Preflight($Config,[bool]$AllowMissingCredential){
    if(-not(Test-Path -LiteralPath $Config.sourceRoot -PathType Container)){throw 'SOURCE_ROOT_MISSING'}
    if(-not(Test-Path -LiteralPath $Config.pythonExe -PathType Leaf)){throw 'PYTHON_MISSING'}
    if(-not(Test-Path -LiteralPath (Join-Path $Config.sourceRoot 'era\api\service.py') -PathType Leaf)){throw 'ERA_API_SOURCE_MISSING'}
    Assert-FileHash $Config.collinMdbPath $Config.collinMdbSha256 'COLLIN_MDB'
    Assert-FileHash $Config.collinCodeListPath $Config.collinCodeListSha256 'COLLIN_CODE_LIST'
    if(-not $AllowMissingCredential -and -not(Test-Path -LiteralPath $Config.credentialFile -PathType Leaf)){throw 'DPAPI_CREDENTIAL_MISSING'}
    foreach($directory in @($Config.stateDirectory,$Config.operatorLogDirectory,$Config.diagnosticLogDirectory)){
        if(-not(Test-Path -LiteralPath $directory -PathType Container)){New-Item -ItemType Directory -Path $directory -Force|Out-Null}
    }
}

function Write-OperatorEvent([string]$Path,[string]$Event,[hashtable]$Fields=@{}){
    $record=[ordered]@{utc=[DateTime]::UtcNow.ToString('o');event=$Event}
    foreach($key in $Fields.Keys){$record[$key]=$Fields[$key]}
    Add-Content -LiteralPath $Path -Value ($record|ConvertTo-Json -Compress)
}

function New-RunNonce {
    $bytes=New-Object byte[] 32; $generator=New-Object Security.Cryptography.RNGCryptoServiceProvider
    try{$generator.GetBytes($bytes)}finally{$generator.Dispose()}
    return ([BitConverter]::ToString($bytes)).Replace('-','').ToLowerInvariant()
}

function Get-ApiToken([string]$Path){
    $protected=Import-Clixml -LiteralPath $Path
    if($protected -is [PSCredential]){$plain=$protected.GetNetworkCredential().Password}
    elseif($protected -is [Security.SecureString]){$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($protected)
        try{$plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)}finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)}}
    else{throw 'DPAPI_CREDENTIAL_INVALID'}
    if([string]::IsNullOrWhiteSpace($plain) -or $plain.Length -lt 32){throw 'DPAPI_CREDENTIAL_INVALID'}
    return $plain
}

function Get-ControlPaths($Config){[pscustomobject]@{
    State=Join-Path $Config.stateDirectory 'era-supervisor.json'; Nonce=Join-Path $Config.stateDirectory 'era-supervisor.nonce'
    Intent=Join-Path $Config.stateDirectory 'era-stop-intent.json'; Ack=Join-Path $Config.stateDirectory 'era-stop-ack.json'
    Commit=Join-Path $Config.stateDirectory 'era-stop-commit.json'
}}

function Get-StopHandshakeSeconds($Config){
    return Get-ValidatedHandshakeSeconds $(if($Config.PSObject.Properties['stopHandshakeSeconds']){$Config.stopHandshakeSeconds}else{$null})
}

function Remove-ControlFiles($Paths){
    Remove-Item -LiteralPath $Paths.State,$Paths.Nonce,$Paths.Intent,$Paths.Ack,$Paths.Commit -Force -ErrorAction SilentlyContinue
}

function Get-CompleteValidatedSet($State){
    if($null -eq $State.supervisor -or $null -eq $State.child){throw 'CONTROL_PROCESS_SET_INCOMPLETE'}
    $supervisor=Get-ValidatedProcessHandle $State.supervisor 'era-supervisor.ps1'
    try{$child=Get-ValidatedProcessHandle $State.child 'uvicorn era.api:app'}catch{$supervisor.Handle.Dispose();throw}
    if(-not(Test-CompleteProcessSet $State.supervisor $supervisor.Fingerprint $State.child $child.Fingerprint)){
        $child.Handle.Dispose();$supervisor.Handle.Dispose();throw 'CONTROL_PROCESS_SET_MISMATCH'
    }
    return [pscustomobject]@{Supervisor=$supervisor;Child=$child}
}

function Invoke-CooperativeStop($Config){
    $paths=Get-ControlPaths $Config
    if((Test-Path -LiteralPath $paths.Intent) -or (Test-Path -LiteralPath $paths.Ack) -or
            (Test-Path -LiteralPath $paths.Commit)){throw 'STOP_REQUEST_ACTIVE_OR_REPLAYED'}
    $state=Read-ValidatedControlState $paths.State $paths.Nonce
    if(-not(Test-StaleRunRecord $state)){throw 'CONTROL_STATE_INVALID_FOR_STOP'}
    $validated=Get-CompleteValidatedSet $state
    try{
        $requestNonce=New-RunNonce; $now=[DateTime]::UtcNow
        $handshakeSeconds=Get-StopHandshakeSeconds $Config
        Write-AtomicJson $paths.Intent ([ordered]@{schemaVersion=1;runNonce=$state.runNonce;requestNonce=$requestNonce
            createdUtc=$now.ToString('o');expiresUtc=$now.AddSeconds($handshakeSeconds).ToString('o')})
        $deadline=$now.AddSeconds($handshakeSeconds)
        $ack=$null
        while([DateTime]::UtcNow -lt $deadline){
            if(Test-Path -LiteralPath $paths.Ack){$ack=Get-Content -Raw -LiteralPath $paths.Ack|ConvertFrom-Json;break}
            Start-Sleep -Milliseconds 200
        }
        if($null -eq $ack -or $ack.status -ne 'READY' -or [string]$ack.readyNonce -notmatch '^[a-f0-9]{64}$' -or
            -not[string]::Equals([string]$ack.runNonce,[string]$state.runNonce,[StringComparison]::Ordinal) -or
            -not[string]::Equals([string]$ack.requestNonce,$requestNonce,[StringComparison]::Ordinal)){throw 'STOP_ACK_TIMEOUT_OR_MISMATCH'}
        if([DateTime]::UtcNow -ge $deadline){throw 'STOP_ACK_TIMEOUT_OR_MISMATCH'}
        Write-AtomicJson $paths.Commit ([ordered]@{schemaVersion=1;status='COMMIT';runNonce=$state.runNonce
            requestNonce=$requestNonce;readyNonce=$ack.readyNonce;utc=[DateTime]::UtcNow.ToString('o')})
        $remaining=[Math]::Max(1000,[int](($deadline-[DateTime]::UtcNow).TotalMilliseconds))
        if(-not $validated.Child.Handle.WaitForExit($remaining)){throw 'STOP_CHILD_EXIT_TIMEOUT'}
        if(-not $validated.Supervisor.Handle.WaitForExit($remaining)){throw 'STOP_SUPERVISOR_EXIT_TIMEOUT'}
        Remove-ControlFiles $paths
    }finally{$validated.Child.Handle.Dispose();$validated.Supervisor.Handle.Dispose()}
}

function Resolve-PriorRun($Paths,[string]$OperatorLog){
    $hasState=Test-Path -LiteralPath $Paths.State; $hasNonce=Test-Path -LiteralPath $Paths.Nonce
    if(-not $hasState -and -not $hasNonce){return}
    $state=Read-ValidatedControlState $Paths.State $Paths.Nonce
    if(-not(Test-StaleRunRecord $state)){throw 'PRIOR_RUN_RECONCILIATION_UNPROVEN'}
    try{$recovered=Get-ValidatedProcessHandle $state.child 'uvicorn era.api:app'}
    catch [Microsoft.PowerShell.Commands.ProcessCommandException]{Remove-ControlFiles $Paths;return}
    catch{throw 'PRIOR_RUN_RECONCILIATION_UNPROVEN'}
    try{Stop-ExactProcessHandle $recovered.Handle;Write-OperatorEvent $OperatorLog 'PRIOR_CHILD_RECONCILED'}
    finally{$recovered.Handle.Dispose()}
    Remove-ControlFiles $Paths
}

function Test-AndAcceptStopIntent($Paths,$State,$ExpectedSupervisor,$ExpectedChild){
    if(-not(Test-Path -LiteralPath $Paths.Intent)){return $null}
    if(Test-Path -LiteralPath $Paths.Ack){throw 'STOP_INTENT_REPLAY'}
    $intent=Get-Content -Raw -LiteralPath $Paths.Intent|ConvertFrom-Json
    if([int]$intent.schemaVersion -ne 1 -or $intent.requestNonce -notmatch '^[a-f0-9]{64}$' -or
        $intent.runNonce -ne $State.runNonce -or
        [DateTime]::Parse($intent.expiresUtc).ToUniversalTime() -le [DateTime]::UtcNow){throw 'STOP_INTENT_INVALID_OR_STALE'}
    $actualSupervisor=Get-ProcessFingerprint ([int]$ExpectedSupervisor.pid)
    $actualChild=Get-ProcessFingerprint ([int]$ExpectedChild.pid)
    if(-not(Test-CompleteProcessSet $ExpectedSupervisor $actualSupervisor $ExpectedChild $actualChild)){throw 'STOP_PROCESS_SET_MISMATCH'}
    return $intent
}

function Invoke-SupervisorStopHandshake($Paths,$State,$Intent,[string]$OperatorLog){
    $expires=$null;$readyNonce=$null;$authorized=$false
    try{
        $expires=[DateTime]::Parse($Intent.expiresUtc).ToUniversalTime()
        $readyNonce=New-RunNonce
        Write-AtomicJson $Paths.State ([ordered]@{schemaVersion=2;phase='READY';runNonce=$State.runNonce
            supervisor=$State.supervisor;child=$State.child})
        Write-AtomicJson $Paths.Ack ([ordered]@{schemaVersion=1;status='READY';runNonce=$State.runNonce
            requestNonce=$Intent.requestNonce;readyNonce=$readyNonce;expiresUtc=$expires.ToString('o');utc=[DateTime]::UtcNow.ToString('o')})
        while($true){
            if(Test-Path -LiteralPath $Paths.Commit){
                if((Get-Item -LiteralPath $Paths.Commit).LastWriteTimeUtc -gt $expires){throw 'STOP_COMMIT_INVALID_OR_STALE'}
                $commit=Get-Content -Raw -LiteralPath $Paths.Commit|ConvertFrom-Json
                if(-not(Test-StopCommitRecord $commit $State.runNonce $Intent.requestNonce $readyNonce $expires)){
                    throw 'STOP_COMMIT_INVALID_OR_STALE'
                }
                # Authorization becomes irrevocable at successful commit validation, before any optional state update.
                $authorized=$true
                try{Write-AtomicJson $Paths.State ([ordered]@{schemaVersion=2;phase='COMMITTED';runNonce=$State.runNonce
                        supervisor=$State.supervisor;child=$State.child})}catch{}
                return $true
            }
            if([DateTime]::UtcNow -gt $expires){break}
            Start-Sleep -Milliseconds 100
        }
        try{Write-OperatorEvent $OperatorLog 'STOP_REQUEST_EXPIRED'}catch{}
    }catch{
        if($authorized){return $true}
        try{Write-OperatorEvent $OperatorLog 'STOP_REQUEST_REJECTED'}catch{}
    }
    try{Remove-Item -LiteralPath $Paths.Intent,$Paths.Ack,$Paths.Commit -Force -ErrorAction SilentlyContinue}catch{}
    try{Write-AtomicJson $Paths.State $State}catch{try{Write-OperatorEvent $OperatorLog 'STOP_RECOVERY_STATE_WRITE_UNPROVEN'}catch{}}
    return $false
}

$controlConfig=Read-Config $ConfigPath -ControlOnly
if($Mode -eq 'TaskPreview'){[ordered]@{taskName='EnTrus ERA Private Beta';executable='powershell.exe'
    arguments="-NoProfile -NonInteractive -ExecutionPolicy AllSigned -File `"$PSCommandPath`" -Mode Run -ConfigPath `"$((Resolve-Path $ConfigPath).Path)`""
    multipleInstances='IgnoreNew';taskRestartPolicy='Supervisor-level failure only';credentialMaterialIncluded=$false;registrationPerformed=$false}|ConvertTo-Json;exit 0}
if($Mode -eq 'Stop'){Invoke-CooperativeStop $controlConfig;Write-Output 'ERA_PHASE_A1_R2_STOP: COMPLETE';exit 0}
if($Mode -eq 'Restart'){Invoke-CooperativeStop $controlConfig;$Mode='Run'}

$config=Read-Config $ConfigPath
if($Mode -eq 'Run'){
    $runIdentity=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    if(-not[string]::Equals($runIdentity,[string]$config.serviceIdentitySid,[StringComparison]::OrdinalIgnoreCase)){
        throw 'SERVICE_IDENTITY_MISMATCH'
    }
}
Invoke-Preflight $config ($VerificationOnly.IsPresent)
if($Mode -eq 'Preflight'){Write-Output 'ERA_PHASE_A1_R2_PREFLIGHT: PASS';exit 0}
$operatorLog=Join-Path $config.operatorLogDirectory 'era-operator.jsonl';$paths=Get-ControlPaths $config
$lock=$null;$child=$null;$stateEstablished=$false;$cleanExit=$false
try{
    $lock=New-SecureGlobalMutex 'Global\EnTrus.ERA.PrivateBeta.Supervisor' ([string]$config.serviceIdentitySid)
    $supervisorIdentity=Get-ProcessFingerprint $PID
    if($supervisorIdentity.commandLine -notlike '*era-supervisor.ps1*'){throw 'SUPERVISOR_FINGERPRINT_CAPABILITY_UNPROVEN'}
    Resolve-PriorRun $paths $operatorLog
    $runNonce=New-RunNonce;Set-Content -LiteralPath $paths.Nonce -Value $runNonce -NoNewline -Encoding ASCII
    Write-AtomicJson $paths.State ([ordered]@{schemaVersion=2;phase='STARTING';runNonce=$runNonce;supervisor=$supervisorIdentity;child=$null})
    Remove-Item -LiteralPath $paths.Intent,$paths.Ack,$paths.Commit -Force -ErrorAction SilentlyContinue
    $token=Get-ApiToken $config.credentialFile;$crashTimes=[Collections.Generic.List[DateTime]]::new()
    $diagnosticTimes=[Collections.Generic.List[DateTime]]::new();$sequence=0;$stopRequested=$false;$previousReason='INITIAL'
    while(-not $stopRequested){
        Rotate-ClosedLog $operatorLog ([long]$config.maxLogBytes) ([int]$config.logRetentionCount)
        Remove-ExpiredDiagnosticLogs $config.diagnosticLogDirectory ([int]$config.logRetentionCount)
        $now=[DateTime]::UtcNow;$cutoff=$now.AddSeconds(-[int]$config.restartWindowSeconds)
        while($crashTimes.Count -and $crashTimes[0] -lt $cutoff){$crashTimes.RemoveAt(0)}
        if($previousReason -eq 'CRASH'){$crashTimes.Add($now)}
        if($crashTimes.Count -ge [int]$config.maxChildRestarts){throw 'CRASH_RESTART_BUDGET_EXHAUSTED'}
        $sequence++;$stdoutLog=Join-Path $config.diagnosticLogDirectory "era-diagnostic-$runNonce-$sequence-stdout.log"
        $stderrLog=Join-Path $config.diagnosticLogDirectory "era-diagnostic-$runNonce-$sequence-stderr.log"
        $env:ERA_API_BEARER_TOKEN=$token;$env:ERA_COLLIN_MDB_PATH=$config.collinMdbPath
        $env:ERA_COLLIN_CODE_LIST_PATH=$config.collinCodeListPath;$env:ERA_SERVICE_VERSION=$config.serviceVersion
        $arguments=@('-B','-m','uvicorn','era.api:app','--host','127.0.0.1','--port',[string]$config.port,'--no-access-log','--log-level','warning')
        $child=Start-Process -FilePath $config.pythonExe -ArgumentList $arguments -WorkingDirectory $config.sourceRoot `
            -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -PassThru -WindowStyle Hidden
        Remove-Item Env:ERA_API_BEARER_TOKEN -ErrorAction SilentlyContinue
        try{$childIdentity=Get-ProcessFingerprint $child.Id
            if($childIdentity.parentPid -ne $PID -or $childIdentity.commandLine -notlike '*uvicorn*era.api:app*'){throw 'CHILD_IDENTITY_ESTABLISHMENT_FAILED'}}
        catch{Stop-ExactProcessHandle $child;throw 'CHILD_IDENTITY_ESTABLISHMENT_FAILED'}
        $state=[ordered]@{schemaVersion=2;phase='RUNNING';runNonce=$runNonce;supervisor=$supervisorIdentity;child=$childIdentity}
        Write-AtomicJson $paths.State $state;$stateEstablished=$true;Write-OperatorEvent $operatorLog 'CHILD_STARTED' @{pid=$child.Id;version=$config.serviceVersion}
        $deadline=[DateTime]::UtcNow.AddSeconds([int]$config.healthStartupSeconds);$healthy=$false
        while(-not $child.HasExited -and [DateTime]::UtcNow -lt $deadline){try{$health=Invoke-RestMethod -Uri "http://127.0.0.1:$($config.port)/healthz" -TimeoutSec 2
                if($health.status -eq 'ok'){$healthy=$true;break}}catch{Start-Sleep -Milliseconds 500}}
        if(-not $healthy){Stop-ExactProcessHandle $child;Write-OperatorEvent $operatorLog 'HEALTH_STARTUP_FAILED';$previousReason='CRASH';continue}
        Write-OperatorEvent $operatorLog 'HEALTHY';$previousReason='CRASH'
        while(-not $child.HasExited){
            Start-Sleep -Seconds ([int]$config.healthIntervalSeconds)
            Rotate-ClosedLog $operatorLog ([long]$config.maxLogBytes) ([int]$config.logRetentionCount)
            $intent=$null
            try{$intent=Test-AndAcceptStopIntent $paths $state $supervisorIdentity $childIdentity}
            catch{try{Write-OperatorEvent $operatorLog 'STOP_REQUEST_REJECTED'}catch{}
                Remove-Item -LiteralPath $paths.Intent -Force -ErrorAction SilentlyContinue;continue}
            if($intent){
                if(Invoke-SupervisorStopHandshake $paths $state $intent $operatorLog){
                    # A valid atomic COMMIT is the authorization boundary. Client presence is irrelevant after it.
                    $stopRequested=$true;Stop-ExactProcessHandle $child;break
                }
                continue
            }
            if(Test-LogNeedsRotation @($stdoutLog,$stderrLog) ([long]$config.maxLogBytes)){
                $decision=Get-DiagnosticRestartDecision $diagnosticTimes ([DateTime]::UtcNow) ([int]$config.restartWindowSeconds) `
                    ([int]$config.diagnosticRestartCooldownSeconds) ([int]$config.maxDiagnosticRestarts)
                if($decision -eq 'EXHAUSTED'){Stop-ExactProcessHandle $child;throw 'DIAGNOSTIC_RESTART_BUDGET_EXHAUSTED'}
                if($decision -eq 'ALLOW'){$diagnosticTimes.Add([DateTime]::UtcNow);Write-OperatorEvent $operatorLog 'DIAGNOSTIC_BOUND_RESTART';
                    Stop-ExactProcessHandle $child;$previousReason='DIAGNOSTIC';break}
                $sizes=@();foreach($diagnosticPath in @($stdoutLog,$stderrLog)){
                    $sizes+=if(Test-Path $diagnosticPath){(Get-Item $diagnosticPath).Length}else{0}}
                $largest=($sizes|Measure-Object -Maximum).Maximum
                if($largest -ge (2*[long]$config.maxLogBytes)){Stop-ExactProcessHandle $child;throw 'DIAGNOSTIC_HARD_LIMIT_REACHED'}}
            try{$null=Invoke-RestMethod -Uri "http://127.0.0.1:$($config.port)/healthz" -TimeoutSec 2}
            catch{Write-OperatorEvent $operatorLog 'HEALTH_CHECK_FAILED';Stop-ExactProcessHandle $child;$previousReason='CRASH'}
        }
        $child.WaitForExit();Write-OperatorEvent $operatorLog 'CHILD_EXITED' @{exitCode=$child.ExitCode}
    }
    $cleanExit=$true
}finally{
    Remove-Item Env:ERA_API_BEARER_TOKEN -ErrorAction SilentlyContinue
    $cleanupProven=$true
    if($child -and -not $child.HasExited){try{Stop-ExactProcessHandle $child}catch{$cleanupProven=$false;Write-OperatorEvent $operatorLog 'CHILD_CLEANUP_UNPROVEN'}}
    if($cleanupProven -and $cleanExit){Remove-Item -LiteralPath $paths.State,$paths.Nonce -Force -ErrorAction SilentlyContinue}
    elseif($cleanupProven -and -not $stateEstablished){Remove-ControlFiles $paths}
    Exit-SecureGlobalMutex $lock
    if(-not $cleanupProven){throw 'CHILD_CLEANUP_UNPROVEN'}
}
