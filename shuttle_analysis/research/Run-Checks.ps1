param([string]$PythonExecutable = '')
$ErrorActionPreference = 'Stop'
if (-not $PythonExecutable) {
    $taskRuntime = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $taskRuntime) { $PythonExecutable = $taskRuntime }
    else { $PythonExecutable = 'python' }
}
$env:PYTHONIOENCODING = 'utf-8'
& $PythonExecutable (Join-Path $PSScriptRoot 'verify_handoff.py')
if ($LASTEXITCODE -ne 0) { throw 'Handoff verification failed.' }
& $PythonExecutable (Join-Path $PSScriptRoot 'capacity_examples.py')
if ($LASTEXITCODE -ne 0) { throw 'Illustrative calculation check failed.' }
