$ErrorActionPreference = 'Stop'
$taskPidPath = Join-Path $PSScriptRoot 'runtime\server.pid'
if (-not (Test-Path -LiteralPath $taskPidPath)) { Write-Output 'No server PID recorded.'; return }
$taskOwnedPid = [int](Get-Content -LiteralPath $taskPidPath)
$taskProcess = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $taskOwnedPid)
if (-not $taskProcess) { Write-Output 'Server already stopped.'; return }
$taskServer = Join-Path $PSScriptRoot 'server.py'
if ($taskProcess.CommandLine.IndexOf($taskServer,[System.StringComparison]::OrdinalIgnoreCase) -lt 0) { throw 'PID owner mismatch; refusing to stop another process.' }
Stop-Process -Id $taskOwnedPid
Write-Output 'Stopped this app server.'
