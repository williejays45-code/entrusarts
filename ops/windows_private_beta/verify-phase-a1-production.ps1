[CmdletBinding()]param()
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'phase-a1-core.ps1')
$results=[ordered]@{};$unproven=[ordered]@{};$child=$null
try{
    $marker='ERA_R1_PRODUCTION_FINGERPRINT_'+[Guid]::NewGuid().ToString('N')
    $child=Start-Process powershell.exe -ArgumentList @('-NoProfile','-NonInteractive','-Command',"Start-Sleep -Seconds 30 # $marker") -PassThru -WindowStyle Hidden
    Start-Sleep -Milliseconds 400
    try{$fingerprint=Get-ProcessFingerprint $child.Id
        $results.cim_lookup=$null -ne $fingerprint
        $results.executable_path=[string]::Equals([IO.Path]::GetFullPath($child.Path),$fingerprint.executablePath,[StringComparison]::OrdinalIgnoreCase)
        $results.command_line=$fingerprint.commandLine -like "*$marker*"
        $results.parent_process=$fingerprint.parentPid -eq $PID
        $results.creation_time=$fingerprint.creationUtcTicks -eq $child.StartTime.ToUniversalTime().Ticks
        $validated=Get-ValidatedProcessHandle $fingerprint $marker;try{$results.production_handle_validation=$validated.Handle.Id -eq $child.Id}finally{$validated.Handle.Dispose()}
    }catch{
        foreach($name in @('cim_lookup','executable_path','command_line','parent_process','creation_time','production_handle_validation')){
            $unproven[$name]="CIM unavailable under current policy: $($_.Exception.GetType().Name)"}
    }
    $unproven.cim_denial_cleanup='Requires a disposable host identity with deliberately denied CIM and supervisor-level observation; source path uses retained Process handle.'
}finally{if($child -and -not $child.HasExited){Stop-ExactProcessHandle $child};if($child){$child.Dispose()}}
$failed=0;foreach($entry in $results.GetEnumerator()){$status=if($entry.Value){'PASS'}else{'FAIL';$failed++};Write-Output "$($entry.Key): $status"}
foreach($entry in $unproven.GetEnumerator()){Write-Output "$($entry.Key): UNPROVEN - $($entry.Value)"}
Write-Output "PRODUCTION FINGERPRINT: PASS=$($results.Count-$failed) FAIL=$failed UNPROVEN=$($unproven.Count)"
# Exit contract: 0=all executed checks PASS, 1=FAIL, 2=UNPROVEN/non-success. CI must accept only 0.
if($failed){exit 1};if($unproven.Count){exit 2}
