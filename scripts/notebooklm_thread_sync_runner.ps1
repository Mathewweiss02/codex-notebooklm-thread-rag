param(
  [Parameter(Mandatory = $true)]
  [string] $Config,
  [switch] $DryRun,
  [switch] $ReconcileOnly
)

$ErrorActionPreference = "Stop"

function Write-AtomicJson {
  param([string] $Path, [object] $Value)
  $directory = Split-Path -Parent $Path
  if (-not (Test-Path -LiteralPath $directory)) { New-Item -ItemType Directory -Path $directory -Force | Out-Null }
  $temporary = Join-Path $directory (".{0}.{1}.tmp" -f (Split-Path -Leaf $Path), $PID)
  $Value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $temporary -Encoding UTF8
  Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Write-AppendOnlyJson {
  param([string] $Path, [object] $Value)
  $directory = Split-Path -Parent $Path
  if (-not (Test-Path -LiteralPath $directory)) { New-Item -ItemType Directory -Path $directory -Force | Out-Null }
  if (Test-Path -LiteralPath $Path) { throw "Append-only evidence already exists: $Path" }
  $temporary = Join-Path $directory (".{0}.{1}.{2}.tmp" -f (Split-Path -Leaf $Path), $PID, [guid]::NewGuid().ToString("N"))
  try {
    $Value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $temporary -Encoding UTF8
    [System.IO.File]::Move($temporary, $Path)
  } catch {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue }
    throw
  }
}

function New-SoakEvidence {
  param([object] $Run)
  $steps = @($Run.Steps | ForEach-Object {
      [ordered]@{
        Label = [string]$_.Label
        ExitCode = [int]$_.ExitCode
        DurationMs = [int]$_.DurationMs
      }
    })
  return [ordered]@{
    ContractVersion = "temporal-soak-evidence-v1"
    CompletedAt = [string]$Run.CompletedAt
    Status = [string]$Run.Status
    DryRun = [bool]$Run.DryRun
    ReconcileOnly = [bool]$Run.ReconcileOnly
    Steps = $steps
    Resource = $Run.Resource
  }
}

function Convert-ToSafeDiagnosticLine {
  param([object] $Value)
  $line = [string]$Value
  $flags = @([regex]::Matches($line, '(?i)--[a-z0-9-]+') | ForEach-Object { $_.Value.ToLowerInvariant() } | Select-Object -Unique)
  if ($flags.Count -eq 0) { return "<native-output>" }
  return "flags=$($flags -join ',')"
}

$resourceSamples = @()

function Add-ResourceSample {
  try {
    $process = Get-Process -Id $PID -ErrorAction Stop
    $script:resourceSamples += [pscustomobject]@{
      WorkingSetBytes = [int64]$process.WorkingSet64
      PrivateBytes = [int64]$process.PrivateMemorySize64
      HandleCount = [int64]$process.HandleCount
      ProcessorTimeMs = [math]::Round($process.TotalProcessorTime.TotalMilliseconds, 3)
    }
  } catch {
    # Resource diagnostics are supplemental; a disappearing process must not
    # hide the primary runner result or write exception details to the report.
  }
}

function Get-ResourceSummary {
  $samples = @($script:resourceSamples)
  if ($samples.Count -eq 0) {
    return [ordered]@{
      SampleCount = 0
      Available = $false
    }
  }
  $workingSet = @($samples | ForEach-Object { [int64]$_.WorkingSetBytes })
  $privateBytes = @($samples | ForEach-Object { [int64]$_.PrivateBytes })
  $handles = @($samples | ForEach-Object { [int64]$_.HandleCount })
  $processorTime = @($samples | ForEach-Object { [double]$_.ProcessorTimeMs })
  return [ordered]@{
    SampleCount = $samples.Count
    Available = $true
    WorkingSetStartBytes = $workingSet[0]
    WorkingSetEndBytes = $workingSet[$workingSet.Count - 1]
    WorkingSetPeakBytes = [int64](($workingSet | Measure-Object -Maximum).Maximum)
    WorkingSetDeltaBytes = [int64]($workingSet[$workingSet.Count - 1] - $workingSet[0])
    PrivateBytesStart = $privateBytes[0]
    PrivateBytesEnd = $privateBytes[$privateBytes.Count - 1]
    PrivateBytesPeak = [int64](($privateBytes | Measure-Object -Maximum).Maximum)
    PrivateBytesDelta = [int64]($privateBytes[$privateBytes.Count - 1] - $privateBytes[0])
    HandleCountStart = $handles[0]
    HandleCountEnd = $handles[$handles.Count - 1]
    HandleCountPeak = [int64](($handles | Measure-Object -Maximum).Maximum)
    HandleCountDelta = [int64]($handles[$handles.Count - 1] - $handles[0])
    ProcessorTimeDeltaMs = [math]::Round($processorTime[$processorTime.Count - 1] - $processorTime[0], 3)
  }
}

function Invoke-Checked {
  param([string] $Executable, [string[]] $Arguments, [string] $Label)
  $started = Get-Date
  if (-not (Test-Path -LiteralPath $Executable) -and -not (Get-Command $Executable -ErrorAction SilentlyContinue)) {
    throw "$Label executable not found: $Executable"
  }
  $priorPreference = $ErrorActionPreference
  $hasNativePreference = Test-Path variable:PSNativeCommandUseErrorActionPreference
  if ($hasNativePreference) { $priorNativePreference = $PSNativeCommandUseErrorActionPreference }
  try {
    $ErrorActionPreference = "Continue"
    if ($hasNativePreference) { $PSNativeCommandUseErrorActionPreference = $false }
    $output = @(& $Executable @Arguments 2>&1)
    $exitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $priorPreference
    if ($hasNativePreference) { $PSNativeCommandUseErrorActionPreference = $priorNativePreference }
  }
  Add-ResourceSample
  if ($exitCode -ne 0) {
    $safeTail = @($output | Select-Object -Last 12 | ForEach-Object { Convert-ToSafeDiagnosticLine $_ })
    throw "$Label failed with exit code $exitCode. $($safeTail -join ' | ')"
  }
  return [pscustomobject]@{
    Label = $Label
    ExitCode = $exitCode
    DurationMs = [math]::Round(((Get-Date) - $started).TotalMilliseconds)
    OutputTail = @($output | Select-Object -Last 8 | ForEach-Object { Convert-ToSafeDiagnosticLine $_ })
  }
}

$configPath = (Resolve-Path -LiteralPath $Config).Path
$settings = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$required = @("Device", "ProjectionRoot", "Profile", "NotebookId", "NodePath", "PythonPath", "NotebookLmCli", "ProjectionScript", "SyncScript")
foreach ($name in $required) {
  if (-not $settings.$name) { throw "Missing required config field: $name" }
}
$threadIds = @($settings.ThreadIds | Where-Object { $_ })
if ($threadIds.Count -eq 0 -and $settings.AllowAllThreads -ne $true) {
  throw "ThreadIds is empty. Set AllowAllThreads=true explicitly only after source-budget planning."
}

$hasher = [System.Security.Cryptography.SHA256]::Create()
try { $hash = $hasher.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($configPath)) } finally { $hasher.Dispose() }
$hashText = ([System.BitConverter]::ToString($hash)).Replace("-", "")
$mutexName = "Global\CodexThreadRag-" + $hashText.Substring(0, 20)
$mutex = [System.Threading.Mutex]::new($false, $mutexName)
$hasMutex = $false
$run = [ordered]@{
  StartedAt = (Get-Date).ToUniversalTime().ToString("o")
  ConfigName = Split-Path -Leaf $configPath
  Device = $settings.Device
  Profile = $settings.Profile
  DryRun = [bool]$DryRun
  ReconcileOnly = [bool]$ReconcileOnly
  Steps = @()
  Status = "running"
}
$root = [string]$settings.ProjectionRoot
$soakEvidenceRoot = if ($settings.SoakEvidenceRoot) { [string]$settings.SoakEvidenceRoot } else { Join-Path $root "soak-evidence" }
Add-ResourceSample

try {
  $root = [System.IO.Path]::GetFullPath([string]$settings.ProjectionRoot)
  $soakEvidenceRoot = if ($settings.SoakEvidenceRoot) {
    [System.IO.Path]::GetFullPath([string]$settings.SoakEvidenceRoot)
  } else {
    [System.IO.Path]::GetFullPath((Join-Path $root "soak-evidence"))
  }
  $rootPrefix = $root.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
  if (-not $soakEvidenceRoot.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "SoakEvidenceRoot must remain inside ProjectionRoot."
  }

  $hasMutex = $mutex.WaitOne(0)
  if (-not $hasMutex) {
    $run.Status = "skipped-overlap"
    return
  }

  $runsDir = Join-Path $root "runs"
  $runnerStatePath = Join-Path $root "runner_state.json"
  $runnerState = if (Test-Path -LiteralPath $runnerStatePath) { Get-Content -Raw -LiteralPath $runnerStatePath | ConvertFrom-Json } else { [pscustomobject]@{} }

  if (-not $ReconcileOnly -and $settings.AutoEnroll -eq $true) {
    if (-not $settings.EnrollmentScript) { throw "AutoEnroll requires EnrollmentScript in config." }
    $enrollmentArgs = @([string]$settings.EnrollmentScript, "--config", $configPath)
    if (-not $DryRun) { $enrollmentArgs += "--apply" }
    $run.Steps += Invoke-Checked -Executable ([string]$settings.PythonPath) -Arguments $enrollmentArgs -Label "auto-enroll"
    $settings = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
    $threadIds = @($settings.ThreadIds | Where-Object { $_ })
    if ($threadIds.Count -eq 0 -and $settings.AllowAllThreads -ne $true) { throw "Automatic enrollment left the explicit task scope empty." }
  }

  $refreshAuth = if ($null -ne $settings.RefreshAuth) { $settings.RefreshAuth -ne $false } elseif ($null -ne $settings.RefreshMasterToken) { $settings.RefreshMasterToken -ne $false } else { $true }
  if ($refreshAuth) {
    $run.Steps += Invoke-Checked -Executable ([string]$settings.NotebookLmCli) -Arguments @("-p", [string]$settings.Profile, "auth", "refresh", "--verify") -Label "auth-refresh"
  }

  $now = Get-Date
  $reconcileHour = if ($null -ne $settings.ReconcileHour) { [int]$settings.ReconcileHour } else { 3 }
  $today = $now.ToString("yyyy-MM-dd")
  $isReconcileDue = $now.Hour -ge $reconcileHour -and [string]$runnerState.LastReconcileDate -ne $today

  if (-not $ReconcileOnly) {
    $projectionArgs = @(
      [string]$settings.ProjectionScript,
      "--device", [string]$settings.Device,
      "--out", $root,
      "--quiet-minutes", [string]$settings.QuietMinutes,
      "--hard-max-hours", [string]$settings.HardMaxHours,
      "--max-words", [string]$settings.MaxWords,
      "--max-message-chars", [string]$settings.MaxMessageChars,
      "--max-line-bytes", [string]$settings.MaxLineBytes
    )
    foreach ($threadId in $threadIds) { $projectionArgs += @("--thread", [string]$threadId) }
    # Runner dry-run still materializes the sanitized local projection/state;
    # only the NotebookLM sync step is remote-write-free.
    $run.Steps += Invoke-Checked -Executable ([string]$settings.NodePath) -Arguments $projectionArgs -Label "projection"

    if ($settings.TemporalRefresh -eq $true) {
      if (-not $settings.TemporalRefreshScript) { throw "TemporalRefresh requires TemporalRefreshScript in config." }
      if (-not $settings.TemporalRoot) { throw "TemporalRefresh requires TemporalRoot in config." }
      $temporalArgs = @(
        [string]$settings.TemporalRefreshScript,
        "--state", (Join-Path $root "state.json"),
        "--root", [string]$settings.TemporalRoot,
        "--node", [string]$settings.NodePath
      )
      if ($settings.TemporalManifestScript) { $temporalArgs += @("--manifest-script", [string]$settings.TemporalManifestScript) }
      if ($settings.TemporalExtractScript) { $temporalArgs += @("--extract-script", [string]$settings.TemporalExtractScript) }
      if ($settings.TemporalTimeoutSeconds) { $temporalArgs += @("--timeout-seconds", [string]$settings.TemporalTimeoutSeconds) }
      if ($settings.TemporalSnapshotAttempts) { $temporalArgs += @("--snapshot-attempts", [string]$settings.TemporalSnapshotAttempts) }
      if ($settings.MaxMessageChars) { $temporalArgs += @("--max-message-chars", [string]$settings.MaxMessageChars) }
      if ($settings.MaxLineBytes) { $temporalArgs += @("--max-line-bytes", [string]$settings.MaxLineBytes) }
      if ($DryRun) { $temporalArgs += "--dry-run" }
      $run.Steps += Invoke-Checked -Executable ([string]$settings.PythonPath) -Arguments $temporalArgs -Label "temporal-refresh"
    }

    $syncArgs = @(
      [string]$settings.SyncScript,
      "--state", (Join-Path $root "state.json"),
      "--profile", [string]$settings.Profile,
      "--notebook-id", [string]$settings.NotebookId,
      "--wait-timeout", [string]$settings.WaitTimeout
    )
    if ($settings.SwapOld -ne $false) { $syncArgs += "--swap-old" }
    if ($settings.RejectUntrackedSources -eq $true) { $syncArgs += "--reject-untracked-sources" }
    if ($DryRun) { $syncArgs += "--dry-run" }
    $run.Steps += Invoke-Checked -Executable ([string]$settings.PythonPath) -Arguments $syncArgs -Label "sync"
  }

  if (($ReconcileOnly -or $isReconcileDue) -and -not $DryRun) {
    $validateArgs = @(
      [string]$settings.SyncScript,
      "--state", (Join-Path $root "state.json"),
      "--profile", [string]$settings.Profile,
      "--notebook-id", [string]$settings.NotebookId,
      "--validate-only"
    )
    if ($settings.RejectUntrackedSources -eq $true) { $validateArgs += "--reject-untracked-sources" }
    $run.Steps += Invoke-Checked -Executable ([string]$settings.PythonPath) -Arguments $validateArgs -Label "nightly-reconcile"
    $runnerState | Add-Member -NotePropertyName LastReconcileDate -NotePropertyValue $today -Force
    $runnerState | Add-Member -NotePropertyName LastReconcileAt -NotePropertyValue ((Get-Date).ToUniversalTime().ToString("o")) -Force
  }

  if ($settings.RetentionEnabled -eq $true -and $settings.RetentionScript) {
    $retentionArgs = @(
      [string]$settings.RetentionScript,
      "--root", $root,
      "--projection-revisions", [string]$settings.ProjectionRevisions,
      "--retention-days", [string]$settings.RetentionDays,
      "--max-run-reports", [string]$settings.MaxRunReports,
      "--max-search-reports", [string]$settings.MaxSearchReports
    )
    if ($settings.SearchReportsRoot) { $retentionArgs += @("--search-root", [string]$settings.SearchReportsRoot) }
    if ($settings.RetentionApply -eq $true -and -not $DryRun) { $retentionArgs += "--apply" }
    $run.Steps += Invoke-Checked -Executable ([string]$settings.PythonPath) -Arguments $retentionArgs -Label "retention"
  }

  $runnerState | Add-Member -NotePropertyName LastSuccessAt -NotePropertyValue ((Get-Date).ToUniversalTime().ToString("o")) -Force
  Write-AtomicJson -Path $runnerStatePath -Value $runnerState
  $run.Status = "ok"
} catch {
  $run.Status = "error"
  $run.Error = "$($_.Exception.GetType().Name): runner step failed"
  throw
} finally {
  $run.CompletedAt = (Get-Date).ToUniversalTime().ToString("o")
  Add-ResourceSample
  $run.Resource = Get-ResourceSummary
  if ($run.Status -ne "skipped-overlap") {
    $runnerStatePath = Join-Path ([string]$settings.ProjectionRoot) "runner_state.json"
    $finalRunnerState = if (Test-Path -LiteralPath $runnerStatePath) { Get-Content -Raw -LiteralPath $runnerStatePath | ConvertFrom-Json } else { [pscustomobject]@{} }
    $finalRunnerState | Add-Member -NotePropertyName LastAttemptAt -NotePropertyValue $run.CompletedAt -Force
    $finalRunnerState | Add-Member -NotePropertyName LastStatus -NotePropertyValue $run.Status -Force
    if ($run.Status -eq "error") {
      $finalRunnerState | Add-Member -NotePropertyName LastError -NotePropertyValue ([string]$run.Error) -Force
    } else {
      $finalRunnerState.PSObject.Properties.Remove("LastError")
    }
    Write-AtomicJson -Path $runnerStatePath -Value $finalRunnerState
  }
  $runsDir = Join-Path ([string]$settings.ProjectionRoot) "runs"
  $runPath = Join-Path $runsDir ("runner-{0}-{1}.json" -f (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffZ"), $PID)
  Write-AtomicJson -Path $runPath -Value $run
  $soakEvidencePath = Join-Path $soakEvidenceRoot ("soak-{0}-{1}.json" -f (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffZ"), $PID)
  Write-AppendOnlyJson -Path $soakEvidencePath -Value (New-SoakEvidence -Run $run)
  if ($hasMutex) { $mutex.ReleaseMutex() }
  $mutex.Dispose()
  [pscustomobject]@{ Status = $run.Status; Run = $runPath } | ConvertTo-Json
}
