[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$recordPath = Join-Path $repoRoot 'data\local-processes.json'
if (-not (Test-Path -LiteralPath $recordPath -PathType Leaf)) {
    Write-Output 'No recorded local services. Nothing was stopped.'
    return
}
$document = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
if (-not [String]::Equals($document.repository, $repoRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Recorded repository differs from this checkout. No process was stopped.'
}
foreach ($entry in $document.processes) {
    if ($entry.role -notin @('api', 'worker', 'frontend')) {
        Write-Warning 'Unknown recorded role; skipped.'
        continue
    }
    $processId = [int]$entry.pid
    $snapshot = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
    if (-not $snapshot) { Write-Output "$($entry.role) PID $processId already exited."; continue }
    $sameCommand = [String]::Equals($snapshot.CommandLine, $entry.command_line, [StringComparison]::Ordinal)
    # PowerShell 7 may deserialize ISO JSON strings as DateTime; compare exact
    # UTC ticks rather than allowing a locale-dependent string conversion.
    try {
        $recordedCreation = if ($entry.process_created_at -is [DateTime]) {
            $entry.process_created_at.ToUniversalTime()
        } else {
            [DateTime]::Parse([string]$entry.process_created_at, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
        }
        $sameCreation = $snapshot.CreationDate.ToUniversalTime().Ticks -eq $recordedCreation.Ticks
    } catch {
        $sameCreation = $false
    }
    $belongsToCheckout = $snapshot.CommandLine.IndexOf($repoRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0
    $expectedRole = switch ($entry.role) {
        'api' { $snapshot.CommandLine -match '-m\s+uvicorn\s+backend\.app\.main:app' }
        'worker' { $snapshot.CommandLine -match '-m\s+worker\.worker_main' }
        'frontend' { $snapshot.CommandLine -match 'node_modules[\\/]vite[\\/]bin[\\/]vite\.js' }
    }
    if (-not ($sameCommand -and $sameCreation -and $belongsToCheckout -and $expectedRole)) {
        Write-Warning "Identity check failed for $($entry.role) PID $processId; skipped."
        continue
    }
    # Windows virtualenv python.exe is a launcher. Only its direct Python
    # child with the same validated command line belongs to this role.
    # Console hosts and unrelated descendants are deliberately excluded.
    if ($entry.role -in @('api', 'worker')) {
        $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $processId"
        foreach ($child in $children) {
            $sameChildCommand = [String]::Equals($child.CommandLine, $snapshot.CommandLine, [StringComparison]::Ordinal)
            $isPython = $child.Name -match '^python(?:w)?\.exe$'
            $createdAfterParent = $child.CreationDate -ge $snapshot.CreationDate
            if (-not ($sameChildCommand -and $isPython -and $createdAfterParent)) { continue }
            $currentChild = Get-CimInstance Win32_Process -Filter "ProcessId = $($child.ProcessId)"
            if ($currentChild -and $currentChild.CreationDate -eq $child.CreationDate -and
                [String]::Equals($currentChild.CommandLine, $snapshot.CommandLine, [StringComparison]::Ordinal)) {
                Stop-Process -Id ([int]$child.ProcessId) -ErrorAction Stop
                Write-Output "Stopped $($entry.role) Python child PID $($child.ProcessId)."
            }
        }
    }
    $remainingParent = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
    if ($remainingParent -and $remainingParent.CreationDate -eq $snapshot.CreationDate -and
        [String]::Equals($remainingParent.CommandLine, $snapshot.CommandLine, [StringComparison]::Ordinal)) {
        Stop-Process -Id $processId -ErrorAction Stop
        Write-Output "Stopped $($entry.role) PID $processId."
    } else {
        Write-Output "$($entry.role) launcher PID $processId already exited."
    }
}
Write-Output 'Database, artifacts, process records and logs were preserved.'
