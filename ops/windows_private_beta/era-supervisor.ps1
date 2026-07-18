[CmdletBinding()]
param(
    [ValidateSet('Run', 'Preflight', 'Stop', 'Restart', 'TaskPreview')]
    [string]$Mode = 'Run',
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath,
    [switch]$VerificationOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Read-Config([string]$Path) {
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    $value = Get-Content -Raw -LiteralPath $resolved | ConvertFrom-Json
    foreach ($name in @('sourceRoot','pythonExe','credentialFile','collinMdbPath','collinMdbSha256',
            'collinCodeListPath','collinCodeListSha256','stateDirectory','operatorLogDirectory',
            'diagnosticLogDirectory','host','port','serviceVersion')) {
        if (-not $value.PSObject.Properties[$name] -or [string]::IsNullOrWhiteSpace([string]$value.$name)) {
            throw "CONFIG_MISSING_FIELD:$name"
        }
    }
    if ($value.host -ne '127.0.0.1') { throw 'LOOPBACK_BINDING_REQUIRED' }
    if ([int]$value.port -lt 1024 -or [int]$value.port -gt 65535) { throw 'INVALID_PORT' }
    return $value
}

function Assert-FileHash([string]$Path, [string]$Expected, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "${Label}_MISSING" }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash
    if (-not [string]::Equals($actual, $Expected, [StringComparison]::OrdinalIgnoreCase)) {
        throw "${Label}_HASH_MISMATCH"
    }
}

function Invoke-Preflight($Config, [bool]$AllowMissingCredential) {
    if (-not (Test-Path -LiteralPath $Config.sourceRoot -PathType Container)) { throw 'SOURCE_ROOT_MISSING' }
    if (-not (Test-Path -LiteralPath $Config.pythonExe -PathType Leaf)) { throw 'PYTHON_MISSING' }
    if (-not (Test-Path -LiteralPath (Join-Path $Config.sourceRoot 'era\api\service.py') -PathType Leaf)) {
        throw 'ERA_API_SOURCE_MISSING'
    }
    Assert-FileHash $Config.collinMdbPath $Config.collinMdbSha256 'COLLIN_MDB'
    Assert-FileHash $Config.collinCodeListPath $Config.collinCodeListSha256 'COLLIN_CODE_LIST'
    if (-not $AllowMissingCredential -and -not (Test-Path -LiteralPath $Config.credentialFile -PathType Leaf)) {
        throw 'DPAPI_CREDENTIAL_MISSING'
    }
    foreach ($directory in @($Config.stateDirectory,$Config.operatorLogDirectory,$Config.diagnosticLogDirectory)) {
        if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
            New-Item -ItemType Directory -Path $directory -Force | Out-Null
        }
    }
}

function Rotate-Log([string]$Path, [long]$Limit, [int]$Retention) {
    if (-not (Test-Path -LiteralPath $Path) -or (Get-Item -LiteralPath $Path).Length -lt $Limit) { return }
    for ($index = $Retention - 1; $index -ge 1; $index--) {
        $old = "$Path.$index"; $next = "$Path.$($index + 1)"
        if (Test-Path -LiteralPath $old) { Move-Item -Force -LiteralPath $old -Destination $next }
    }
    Move-Item -Force -LiteralPath $Path -Destination "$Path.1"
}

function Write-OperatorEvent([string]$Path, [string]$Event, [hashtable]$Fields = @{}) {
    $record = [ordered]@{ utc = [DateTime]::UtcNow.ToString('o'); event = $Event }
    foreach ($key in $Fields.Keys) { $record[$key] = $Fields[$key] }
    Add-Content -LiteralPath $Path -Value ($record | ConvertTo-Json -Compress)
}

function Get-ApiToken([string]$Path) {
    $protected = Import-Clixml -LiteralPath $Path
    if ($protected -is [PSCredential]) { $plain = $protected.GetNetworkCredential().Password }
    elseif ($protected -is [Security.SecureString]) {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($protected)
        try { $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    } else { throw 'DPAPI_CREDENTIAL_INVALID' }
    if ([string]::IsNullOrWhiteSpace($plain) -or $plain.Length -lt 32) { throw 'DPAPI_CREDENTIAL_INVALID' }
    return $plain
}

function Stop-ManagedProcess($Config) {
    $pidPath = Join-Path $Config.stateDirectory 'era-supervisor.json'
    if (-not (Test-Path -LiteralPath $pidPath)) { return }
    $state = Get-Content -Raw -LiteralPath $pidPath | ConvertFrom-Json
    foreach ($id in @($state.childPid,$state.supervisorPid)) {
        if ($id -and [int]$id -ne $PID) { Stop-Process -Id ([int]$id) -ErrorAction SilentlyContinue }
    }
    Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
}

$config = Read-Config $ConfigPath
$operatorLog = Join-Path $config.operatorLogDirectory 'era-operator.jsonl'
$diagnosticLog = Join-Path $config.diagnosticLogDirectory 'era-diagnostic-stdout.log'
$diagnosticErrorLog = Join-Path $config.diagnosticLogDirectory 'era-diagnostic-stderr.log'
$pidFile = Join-Path $config.stateDirectory 'era-supervisor.json'

if ($Mode -eq 'TaskPreview') {
    [ordered]@{
        taskName = 'EnTrus ERA Private Beta'
        executable = 'powershell.exe'
        arguments = "-NoProfile -NonInteractive -ExecutionPolicy AllSigned -File `"$PSCommandPath`" -Mode Run -ConfigPath `"$ConfigPath`""
        recoveryAuthority = 'Supervisor owns Uvicorn; Task Scheduler restarts only supervisor-level failure'
        credentialMaterialIncluded = $false
        registrationPerformed = $false
    } | ConvertTo-Json
    exit 0
}

Invoke-Preflight $config ($VerificationOnly.IsPresent)
if ($Mode -eq 'Preflight') { Write-Output 'ERA_PHASE_A_PREFLIGHT: PASS'; exit 0 }
if ($Mode -eq 'Stop') { Stop-ManagedProcess $config; Write-Output 'ERA_PHASE_A_STOP: COMPLETE'; exit 0 }
if ($Mode -eq 'Restart') { Stop-ManagedProcess $config; $Mode = 'Run' }

$createdNew = $false
$mutex = [Threading.Mutex]::new($true, 'Local\EnTrus.ERA.PrivateBeta.Supervisor', [ref]$createdNew)
if (-not $createdNew) { throw 'SUPERVISOR_ALREADY_RUNNING' }

try {
    Rotate-Log $operatorLog ([long]$config.maxLogBytes) ([int]$config.logRetentionCount)
    Rotate-Log $diagnosticLog ([long]$config.maxLogBytes) ([int]$config.logRetentionCount)
    Rotate-Log $diagnosticErrorLog ([long]$config.maxLogBytes) ([int]$config.logRetentionCount)
    $token = Get-ApiToken $config.credentialFile
    $restartTimes = [Collections.Generic.List[DateTime]]::new()
    while ($true) {
        $cutoff = [DateTime]::UtcNow.AddSeconds(-[int]$config.restartWindowSeconds)
        while ($restartTimes.Count -and $restartTimes[0] -lt $cutoff) { $restartTimes.RemoveAt(0) }
        if ($restartTimes.Count -ge [int]$config.maxChildRestarts) { throw 'RESTART_BUDGET_EXHAUSTED' }
        $restartTimes.Add([DateTime]::UtcNow)

        $env:ERA_API_BEARER_TOKEN = $token
        $env:ERA_COLLIN_MDB_PATH = $config.collinMdbPath
        $env:ERA_COLLIN_CODE_LIST_PATH = $config.collinCodeListPath
        $env:ERA_SERVICE_VERSION = $config.serviceVersion
        $arguments = @('-B','-m','uvicorn','era.api:app','--host','127.0.0.1','--port',[string]$config.port,
            '--no-access-log','--log-level','warning')
        $child = Start-Process -FilePath $config.pythonExe -ArgumentList $arguments -WorkingDirectory $config.sourceRoot `
            -RedirectStandardOutput $diagnosticLog -RedirectStandardError $diagnosticErrorLog -PassThru -WindowStyle Hidden
        Remove-Item Env:ERA_API_BEARER_TOKEN -ErrorAction SilentlyContinue
        @{ supervisorPid=$PID; childPid=$child.Id; startedUtc=[DateTime]::UtcNow.ToString('o') } |
            ConvertTo-Json | Set-Content -LiteralPath $pidFile
        Write-OperatorEvent $operatorLog 'CHILD_STARTED' @{ pid=$child.Id; version=$config.serviceVersion }

        $deadline = [DateTime]::UtcNow.AddSeconds([int]$config.healthStartupSeconds)
        $healthy = $false
        while (-not $child.HasExited -and [DateTime]::UtcNow -lt $deadline) {
            try {
                $health = Invoke-RestMethod -Uri "http://127.0.0.1:$($config.port)/healthz" -TimeoutSec 2
                if ($health.status -eq 'ok') { $healthy = $true; break }
            } catch { Start-Sleep -Milliseconds 500 }
        }
        if (-not $healthy) { Stop-Process -Id $child.Id -ErrorAction SilentlyContinue; Write-OperatorEvent $operatorLog 'HEALTH_STARTUP_FAILED'; continue }
        Write-OperatorEvent $operatorLog 'HEALTHY'
        while (-not $child.HasExited) {
            Start-Sleep -Seconds ([int]$config.healthIntervalSeconds)
            try { $null = Invoke-RestMethod -Uri "http://127.0.0.1:$($config.port)/healthz" -TimeoutSec 2 }
            catch { Write-OperatorEvent $operatorLog 'HEALTH_CHECK_FAILED'; Stop-Process -Id $child.Id -ErrorAction SilentlyContinue }
        }
        Write-OperatorEvent $operatorLog 'CHILD_EXITED' @{ exitCode=$child.ExitCode }
    }
} finally {
    Remove-Item Env:ERA_API_BEARER_TOKEN -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    if ($mutex) { $mutex.ReleaseMutex(); $mutex.Dispose() }
}
