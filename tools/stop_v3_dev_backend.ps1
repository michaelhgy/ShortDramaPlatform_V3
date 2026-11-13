$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$listeners = @(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8782 -State Listen -ErrorAction SilentlyContinue)

foreach ($listener in $listeners) {
    $processId = [int]$listener.OwningProcess
    if ($processId -le 0) { continue }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    $commandLine = [string]$process.CommandLine
    $isV3SourceRuntime = $commandLine -match 'run_v2_desktop\.py' -and (
        $commandLine -match [regex]::Escape($projectRoot) -or
        $commandLine -match 'tools\\run_v2_desktop\.py'
    )
    if ($isV3SourceRuntime) {
        Write-Host "Stopping previous V3 backend (PID $processId)..."
        Stop-Process -Id $processId -Force
        Start-Sleep -Milliseconds 500
    } else {
        Write-Host "Port 8782 is occupied by an unrelated process (PID $processId); startup was stopped."
        exit 2
    }
}
exit 0
