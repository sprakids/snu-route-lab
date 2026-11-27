param([int]$Port = 8840)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
try {
    $taskHealth = Invoke-RestMethod -Uri ('http://127.0.0.1:' + $Port + '/api/health') -TimeoutSec 2
    if ($taskHealth.app -eq 'snu-route-lab') { Write-Output ('Already running: http://localhost:' + $Port); return }
} catch { }
$taskListeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($taskListeners) { throw 'The port belongs to another process. Choose a different port.' }
$taskPython = (& python -c 'import sys,json; print(json.dumps(sys.executable))') | ConvertFrom-Json
if (-not (Test-Path -LiteralPath $taskPython -PathType Leaf)) { throw 'Python could not be resolved.' }
$taskRuntime = Join-Path $taskRoot 'runtime'
New-Item -ItemType Directory -Path $taskRuntime -Force | Out-Null
$taskStamp = Get-Date -Format 'yyyyMMdd_HHmmss'
foreach ($taskName in @('server.stdout.log','server.stderr.log')) {
    $taskLog = Join-Path $taskRuntime $taskName
    if (Test-Path -LiteralPath $taskLog) { Copy-Item -LiteralPath $taskLog -Destination (Join-Path $taskRuntime ($taskStamp + '_' + $taskName)) }
}
$taskServer = Join-Path $taskRoot 'server.py'
$taskProcess = Start-Process -FilePath $taskPython -ArgumentList @('-X','utf8',('"' + $taskServer + '"'),'--port',"$Port") -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskRuntime 'server.stdout.log') -RedirectStandardError (Join-Path $taskRuntime 'server.stderr.log') -PassThru
$taskProcess.Id | Set-Content -LiteralPath (Join-Path $taskRuntime 'server.pid')
Write-Output ('Started: http://localhost:' + $Port)
