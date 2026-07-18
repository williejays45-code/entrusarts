[CmdletBinding()]
param([string]$SupervisorPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($SupervisorPath)) {
    $SupervisorPath = Join-Path $PSScriptRoot 'era-supervisor.ps1'
}
$checks = [ordered]@{}
$text = Get-Content -Raw -LiteralPath $SupervisorPath

$checks.loopback_only = $text -match "host -ne '127\.0\.0\.1'" -and $text -match "'--host','127\.0\.0\.1'"
$checks.exact_uvicorn_module = $text -match "'-B','-m','uvicorn','era\.api:app'"
$checks.dpapi_runtime_credential = $text -match 'Import-Clixml' -and $text -notmatch 'ConvertTo-SecureString\s+-AsPlainText'
$checks.token_not_command_line = $text -notmatch "ArgumentList[^\r\n]*ERA_API_BEARER_TOKEN"
$checks.hash_drift_detection = $text -match 'Get-FileHash' -and $text -match 'HASH_MISMATCH'
$checks.single_instance = $text -match 'Threading\.Mutex' -and $text -match 'SUPERVISOR_ALREADY_RUNNING'
$checks.bounded_recovery = $text -match 'RESTART_BUDGET_EXHAUSTED'
$checks.health_polling = $text -match '/healthz'
$checks.controlled_stop_restart = $text -match "ValidateSet\('Run', 'Preflight', 'Stop', 'Restart', 'TaskPreview'\)"
$checks.log_rotation = $text -match 'function Rotate-Log'
$checks.separate_log_channels = $text -match 'operatorLogDirectory' -and $text -match 'diagnosticLogDirectory'
$checks.exception_path_isolated = $text -match 'RedirectStandardError \$diagnosticErrorLog' -and
    $text -notmatch 'Write-OperatorEvent[^\r\n]*(\$_|Exception|diagnostic)'
$checks.access_logs_disabled = $text -match "'--no-access-log'"
$checks.task_preview_only = $text -match 'registrationPerformed = \$false' -and $text -notmatch 'Register-ScheduledTask'
$checks.scheduler_not_child_recovery = $text -match 'Task Scheduler restarts only supervisor-level failure'
$checks.no_account_acl_install = $text -notmatch 'New-LocalUser|icacls|Set-Acl'
$checks.no_system_install = $text -notmatch 'pip install|Install-Package|winget|choco'

$failed = 0
foreach ($entry in $checks.GetEnumerator()) {
    $result = if ($entry.Value) { 'PASS' } else { 'FAIL'; $failed++ }
    Write-Output "$($entry.Key): $result"
}
Write-Output "WINDOWS PRIVATE BETA PHASE A: $($checks.Count - $failed)/$($checks.Count) PASS"
if ($failed) { exit 1 }
