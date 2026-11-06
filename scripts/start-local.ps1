[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pythonExecutable = Join-Path $repoRoot '.venv\Scripts\python.exe'
$viteEntrypoint = Join-Path $repoRoot 'frontend\node_modules\vite\bin\vite.js'
$dataDirectory = Join-Path $repoRoot 'data'
$recordPath = Join-Path $dataDirectory 'local-processes.json'

if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
    throw 'Missing .venv\Scripts\python.exe. Follow the README dependency setup first.'
}
if (-not (Test-Path -LiteralPath $viteEntrypoint -PathType Leaf)) {
    throw 'Missing installed Vite. Run npm ci in frontend before starting.'
}
$nodeExecutable = (Get-Command node -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
foreach ($portNumber in @(8000, 5173)) {
    $listener = Get-NetTCPConnection -LocalPort $portNumber -State Listen -ErrorAction SilentlyContinue
    if ($listener) { throw "Port $portNumber is already in use. No existing process was stopped." }
}
if (Test-Path -LiteralPath $recordPath) {
    $previous = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
    foreach ($entry in $previous.processes) {
        if (Get-Process -Id ([int]$entry.pid) -ErrorAction SilentlyContinue) {
            throw 'A recorded PID is still running. Inspect data/local-processes.json or use scripts/stop-local.ps1 first.'
        }
    }
}
New-Item -ItemType Directory -Path $dataDirectory -Force | Out-Null
$records = [System.Collections.Generic.List[object]]::new()

function Write-ProcessRecords {
    $document = [ordered]@{ repository = $repoRoot; created_at = [DateTime]::UtcNow.ToString('o'); processes = @($records.ToArray()) }
    ConvertTo-Json -InputObject $document -Depth 6 | Set-Content -LiteralPath $recordPath -Encoding UTF8
}

function Start-RecordedProcess {
    param([string]$Role, [string]$Executable, [string[]]$Arguments)
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $dataDirectory "local-$Role.stdout.log") `
        -RedirectStandardError (Join-Path $dataDirectory "local-$Role.stderr.log")
    $snapshot = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)"
    if (-not $snapshot) { throw "The $Role process exited during startup. Inspect data/local-$Role.stderr.log." }
    $records.Add([ordered]@{
        role = $Role; pid = $process.Id; executable = $Executable; arguments = $Arguments
        command_line = $snapshot.CommandLine; process_created_at = $snapshot.CreationDate.ToUniversalTime().ToString('o')
    })
    Write-ProcessRecords
    Write-Output "$Role PID $($process.Id)"
}

$savedEnvironment = @{}
foreach ($variableName in @('SQSP_DATABASE_URL', 'SQSP_QUEUE_BACKEND', 'SQSP_ARTIFACT_ROOT', 'PYTHONDONTWRITEBYTECODE')) {
    $savedEnvironment[$variableName] = [Environment]::GetEnvironmentVariable($variableName, 'Process')
}
$originalDirectory = Get-Location
try {
    Set-Location -LiteralPath $repoRoot
    $env:SQSP_DATABASE_URL = 'sqlite:///./data/sqsp.db'
    $env:SQSP_QUEUE_BACKEND = 'database'
    $env:SQSP_ARTIFACT_ROOT = './data/artifacts'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    & $pythonExecutable -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed; services were not started.' }
    & $pythonExecutable (Join-Path $repoRoot 'scripts\seed_examples.py')
    if ($LASTEXITCODE -ne 0) { throw 'Example ZIP packaging failed; services were not started.' }
    Start-RecordedProcess -Role api -Executable $pythonExecutable -Arguments @('-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', '8000', '--no-access-log')
    Start-RecordedProcess -Role worker -Executable $pythonExecutable -Arguments @('-m', 'worker.worker_main')
    $frontendRoot = Join-Path $repoRoot 'frontend'
    Start-RecordedProcess -Role frontend -Executable $nodeExecutable -Arguments @(('"' + $viteEntrypoint + '"'), ('"' + $frontendRoot + '"'), '--host', '127.0.0.1', '--port', '5173', '--strictPort')
    $ready = $false
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/readyz' -TimeoutSec 2
            $frontendResponse = Invoke-WebRequest -Uri 'http://127.0.0.1:5173/' -UseBasicParsing -TimeoutSec 2
            if ($health.status -eq 'ready' -and $frontendResponse.StatusCode -eq 200) { $ready = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $ready) { throw 'API readiness and frontend HTTP 200 did not both succeed within 30 seconds. Inspect data/local-*.stderr.log; recorded processes remain available for stop-local.ps1.' }
    Write-Output 'Web UI: http://127.0.0.1:5173'
    Write-Output 'API docs: http://127.0.0.1:8000/docs'
    Write-Output 'Stop only recorded services: .\scripts\stop-local.ps1'
} finally {
    Set-Location -LiteralPath $originalDirectory.Path
    foreach ($variableName in $savedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($variableName, $savedEnvironment[$variableName], 'Process')
    }
}
