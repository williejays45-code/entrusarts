Set-StrictMode -Version Latest

function Test-MutexSecurityAuthority($Security,[string[]]$TrustedSids,[string]$ExpectedOwnerSid='') {
    $allow=[Security.AccessControl.AccessControlType]::Allow
    $full=[Security.AccessControl.MutexRights]::FullControl
    $owner=$Security.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if(-not[string]::IsNullOrWhiteSpace($ExpectedOwnerSid)){
        if(-not[string]::Equals($owner,$ExpectedOwnerSid,[StringComparison]::OrdinalIgnoreCase)){return $false}
    }elseif($TrustedSids -notcontains $owner){return $false}
    $rules=$Security.GetAccessRules($true,$false,[Security.Principal.SecurityIdentifier])
    foreach($rule in $rules){if($rule.AccessControlType -eq $allow -and
            $TrustedSids -notcontains $rule.IdentityReference.Value){return $false}}
    foreach($sid in $TrustedSids){$matching=@($rules|Where-Object{$_.AccessControlType -eq $allow -and
            $_.IdentityReference.Value -eq $sid -and ($_.MutexRights -band $full) -eq $full})
        if(-not $matching.Count){return $false}}
    return $true
}

function New-SecureGlobalMutex([string]$Name,[string]$ServiceIdentitySid) {
    if ($Name -notmatch '^Global\\[A-Za-z0-9_.-]+$') { throw 'GLOBAL_MUTEX_NAME_REQUIRED' }
    if($ServiceIdentitySid -notmatch '^S-1-5-21-(?:[0-9]+-){3}[0-9]+$'){throw 'SERVICE_IDENTITY_SID_INVALID'}
    try {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        if(-not[string]::Equals($identity.User.Value,$ServiceIdentitySid,[StringComparison]::OrdinalIgnoreCase)){
            throw 'SERVICE_IDENTITY_MISMATCH'
        }
        $security = New-Object Security.AccessControl.MutexSecurity
        $allow = [Security.AccessControl.AccessControlType]::Allow
        $full = [Security.AccessControl.MutexRights]::FullControl
        foreach ($sid in @(
            (New-Object Security.Principal.SecurityIdentifier($ServiceIdentitySid)),
            (New-Object Security.Principal.SecurityIdentifier('S-1-5-18')),
            (New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544'))
        )) {
            $security.AddAccessRule((New-Object Security.AccessControl.MutexAccessRule($sid, $full, $allow)))
        }
        $created = $false
        $openRights = [Security.AccessControl.MutexRights]::Synchronize -bor
            [Security.AccessControl.MutexRights]::Modify -bor [Security.AccessControl.MutexRights]::ReadPermissions
        try { $mutex = [Threading.Mutex]::new($false, $Name, [ref]$created, $security) }
        catch {
            # Windows PowerShell/.NET Framework can reject the security-bearing constructor when the
            # object already exists. Reopen it with FullControl, then validate its actual ACL below.
            $mutex = [Threading.Mutex]::OpenExisting($Name, $openRights)
            $created = $false
        }
        if (-not $created) {
            $mutex.Dispose()
            $mutex = [Threading.Mutex]::OpenExisting($Name, $openRights)
        }
        $allowedSids = @($ServiceIdentitySid,'S-1-5-18','S-1-5-32-544')
        $actualSecurity = $mutex.GetAccessControl()
        if(-not(Test-MutexSecurityAuthority $actualSecurity $allowedSids $ServiceIdentitySid)){
            $mutex.Dispose();throw 'GLOBAL_MUTEX_AUTHORITY_UNTRUSTED'
        }
        $abandoned = $false
        try { $owned = $mutex.WaitOne(0, $false) }
        catch [Threading.AbandonedMutexException] { $owned = $true; $abandoned = $true }
        if (-not $owned) { $mutex.Dispose(); throw 'SUPERVISOR_ALREADY_RUNNING' }
        return [pscustomobject]@{ Mutex=$mutex; Created=$created; Abandoned=$abandoned }
    } catch {
        if ($_.Exception.Message -eq 'SUPERVISOR_ALREADY_RUNNING') { throw }
        throw "GLOBAL_MUTEX_SECURITY_FAILED:$($_.Exception.GetType().Name)"
    }
}

function Test-StaleRunRecord($State) {
    try{
        if($null -eq $State -or [int]$State.schemaVersion -ne 2 -or $State.phase -ne 'RUNNING'){return $false}
        if([string]$State.runNonce -notmatch '^[a-f0-9]{64}$' -or $null -eq $State.supervisor -or $null -eq $State.child){return $false}
        if([string]$State.supervisor.commandLine -notlike '*era-supervisor.ps1*'){return $false}
        if([string]$State.child.commandLine -notlike '*uvicorn*era.api:app*'){return $false}
        if([int]$State.child.parentPid -ne [int]$State.supervisor.pid){return $false}
        foreach($record in @($State.supervisor,$State.child)){
            foreach($field in @('pid','parentPid','creationUtcTicks','executablePath','commandLine')){
                if([string]::IsNullOrWhiteSpace([string]$record.$field)){return $false}
            }
        }
        return $true
    }catch{return $false}
}

function Test-StopCommitRecord($Commit,[string]$RunNonce,[string]$RequestNonce,[string]$ReadyNonce,[DateTime]$ExpiresUtc) {
    try{
        if($null -eq $Commit){return $false}
        if($Commit.status -ne 'COMMIT'){return $false}
        $committedUtc=[DateTime]::Parse([string]$Commit.utc).ToUniversalTime()
        if($committedUtc -gt $ExpiresUtc){return $false}
        foreach($pair in @(@([string]$Commit.runNonce,$RunNonce),@([string]$Commit.requestNonce,$RequestNonce),
                @([string]$Commit.readyNonce,$ReadyNonce))){
            if(-not[string]::Equals($pair[0],$pair[1],[StringComparison]::Ordinal)){return $false}
        }
        return $true
    }catch{return $false}
}

function Get-ValidatedHandshakeSeconds($Value,[int]$DefaultValue=30) {
    if($null -eq $Value -or [string]::IsNullOrWhiteSpace([string]$Value)){$seconds=$DefaultValue}
    else{$seconds=0;if(-not[int]::TryParse([string]$Value,[ref]$seconds)){throw 'INVALID_STOP_HANDSHAKE_SECONDS'}}
    if($seconds -lt 10 -or $seconds -gt 300){throw 'INVALID_STOP_HANDSHAKE_SECONDS'}
    return $seconds
}

function Exit-SecureGlobalMutex($Lock) {
    if ($null -eq $Lock) { return }
    try { $Lock.Mutex.ReleaseMutex() } finally { $Lock.Mutex.Dispose() }
}

function Get-ProcessFingerprint([int]$ProcessId) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
    if ($null -eq $process) { return $null }
    $creationValue = $process.CreationDate
    $creation = if ($creationValue -is [DateTime]) { $creationValue.ToUniversalTime().Ticks } else {
        [Management.ManagementDateTimeConverter]::ToDateTime([string]$creationValue).ToUniversalTime().Ticks
    }
    return [ordered]@{
        pid = [int]$process.ProcessId
        parentPid = [int]$process.ParentProcessId
        creationUtcTicks = [long]$creation
        executablePath = [IO.Path]::GetFullPath([string]$process.ExecutablePath)
        commandLine = [string]$process.CommandLine
    }
}

function Test-ProcessFingerprint($Expected, $Actual, [string]$RequiredCommand) {
    if ($null -eq $Expected -or $null -eq $Actual) { return $false }
    if ([int]$Expected.pid -ne [int]$Actual.pid) { return $false }
    if ([int]$Expected.parentPid -ne [int]$Actual.parentPid) { return $false }
    if ([long]$Expected.creationUtcTicks -ne [long]$Actual.creationUtcTicks) { return $false }
    if (-not [string]::Equals([IO.Path]::GetFullPath([string]$Expected.executablePath),
            [IO.Path]::GetFullPath([string]$Actual.executablePath), [StringComparison]::OrdinalIgnoreCase)) { return $false }
    if (-not [string]::Equals([string]$Expected.commandLine, [string]$Actual.commandLine,
            [StringComparison]::Ordinal)) { return $false }
    if ([string]::IsNullOrWhiteSpace($RequiredCommand) -or
            [string]$Actual.commandLine -notlike "*$RequiredCommand*") { return $false }
    return $true
}

function Test-CompleteProcessSet($ExpectedSupervisor, $ActualSupervisor, $ExpectedChild, $ActualChild) {
    if (-not (Test-ProcessFingerprint $ExpectedSupervisor $ActualSupervisor 'era-supervisor.ps1')) { return $false }
    if (-not (Test-ProcessFingerprint $ExpectedChild $ActualChild 'uvicorn era.api:app')) { return $false }
    if ([int]$ActualChild.parentPid -ne [int]$ActualSupervisor.pid) { return $false }
    return $true
}

function Write-AtomicJson([string]$Path, $Value) {
    $temporary = "$Path.$([Guid]::NewGuid().ToString('N')).tmp"
    try {
        $Value | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporary -Encoding UTF8
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    } finally { Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue }
}

function Read-ValidatedControlState([string]$StatePath, [string]$NoncePath) {
    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf) -or
            -not (Test-Path -LiteralPath $NoncePath -PathType Leaf)) { throw 'CONTROL_STATE_MISSING' }
    $state = Get-Content -Raw -LiteralPath $StatePath | ConvertFrom-Json
    $nonce = (Get-Content -Raw -LiteralPath $NoncePath).Trim()
    if ($nonce -notmatch '^[a-f0-9]{64}$' -or
            -not [string]::Equals([string]$state.runNonce, $nonce, [StringComparison]::Ordinal)) {
        throw 'CONTROL_NONCE_MISMATCH'
    }
    foreach ($field in @('runNonce','supervisor','child')) {
        if (-not $state.PSObject.Properties[$field]) { throw "CONTROL_STATE_INVALID:$field" }
    }
    return $state
}

function Get-ValidatedProcessHandle($Expected, [string]$RequiredCommand) {
    $handle = Get-Process -Id ([int]$Expected.pid) -ErrorAction Stop
    $actual = Get-ProcessFingerprint ([int]$Expected.pid)
    if (-not (Test-ProcessFingerprint $Expected $actual $RequiredCommand)) { $handle.Dispose(); throw 'PROCESS_IDENTITY_MISMATCH' }
    if ($handle.StartTime.ToUniversalTime().Ticks -ne [long]$actual.creationUtcTicks -or
            -not [string]::Equals([IO.Path]::GetFullPath($handle.Path),[IO.Path]::GetFullPath($actual.executablePath),
                [StringComparison]::OrdinalIgnoreCase)) {
        $handle.Dispose(); throw 'PROCESS_HANDLE_IDENTITY_MISMATCH'
    }
    return [pscustomobject]@{ Handle=$handle; Fingerprint=$actual }
}

function Stop-ExactProcessHandle([Diagnostics.Process]$Process, [int]$TimeoutMilliseconds = 10000) {
    if ($Process.HasExited) { return }
    $Process.Kill()
    if (-not $Process.WaitForExit($TimeoutMilliseconds) -or -not $Process.HasExited) { throw 'EXACT_PROCESS_EXIT_UNPROVEN' }
}

function Test-LogNeedsRotation([string[]]$Paths, [long]$MaximumBytes) {
    foreach ($path in $Paths) {
        if ((Test-Path -LiteralPath $path) -and (Get-Item -LiteralPath $path).Length -ge $MaximumBytes) { return $true }
    }
    return $false
}

function Rotate-ClosedLog([string]$Path, [long]$MaximumBytes, [int]$Retention, [switch]$Force) {
    if ((-not $Force -and $MaximumBytes -lt 1024) -or $Retention -lt 1) { throw 'INVALID_LOG_POLICY' }
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $length = (Get-Item -LiteralPath $Path).Length
    if ($length -eq 0 -or (-not $Force -and $length -lt $MaximumBytes)) { return }
    try {
        $terminal = "$Path.$Retention"
        Remove-Item -LiteralPath $terminal -Force -ErrorAction SilentlyContinue
        for ($index = $Retention - 1; $index -ge 1; $index--) {
            $old = "$Path.$index"
            if (Test-Path -LiteralPath $old) { Move-Item -LiteralPath $old -Destination "$Path.$($index + 1)" -Force }
        }
        Move-Item -LiteralPath $Path -Destination "$Path.1" -Force
    } catch { throw 'LOG_ROTATION_FAILED' }
}

function Remove-ExpiredDiagnosticLogs([string]$Directory, [int]$Retention, [string[]]$Exclude = @()) {
    if ($Retention -lt 1) { throw 'INVALID_LOG_POLICY' }
    $excluded = @($Exclude | ForEach-Object { [IO.Path]::GetFullPath($_) })
    $logs = @(Get-ChildItem -LiteralPath $Directory -Filter 'era-diagnostic-*.log' -File |
        Where-Object { $excluded -notcontains $_.FullName } | Sort-Object LastWriteTimeUtc -Descending)
    foreach ($log in @($logs | Select-Object -Skip $Retention)) {
        try { Remove-Item -LiteralPath $log.FullName -Force } catch { throw 'DIAGNOSTIC_RETENTION_FAILED' }
    }
}

function Get-DiagnosticRestartDecision($RestartTimes,[DateTime]$Now,[int]$WindowSeconds,[int]$CooldownSeconds,[int]$MaximumRestarts) {
    $cutoff=$Now.AddSeconds(-$WindowSeconds)
    while($RestartTimes.Count -and $RestartTimes[0] -lt $cutoff){$RestartTimes.RemoveAt(0)}
    if($RestartTimes.Count -ge $MaximumRestarts){return 'EXHAUSTED'}
    if($RestartTimes.Count -and ($Now-$RestartTimes[$RestartTimes.Count-1]).TotalSeconds -lt $CooldownSeconds){return 'DEFER'}
    return 'ALLOW'
}
