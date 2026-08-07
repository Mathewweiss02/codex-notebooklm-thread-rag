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
  if ($exitCode -ne 0) {
    $safeTail = @($output | Select-Object -Last 12 | ForEach-Object { [string]$_ })
    throw "$Label failed with exit code $exitCode. $($safeTail -join ' | ')"
  }
  return [pscustomobject]@{
    Label = $Label
    ExitCode = $exitCode
    DurationMs = [math]::Round(((Get-Date) - $started).TotalMilliseconds)
    OutputTail = @($output | Select-Object -Last 8 | ForEach-Object { [string]$_ })
  }
}

$configPath = (Resolve-Path -LiteralPath $Config).Path
$settings = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$required = @("Device", "ProjectionRoot", "Profile", "NotebookId", "NodePath", "PythonPath", "NotebookLmCli", "ProjectionScript", "SyncScript")
foreach ($name in $required) {
  if (-not $settings.$name) { throw "Missing required config field: $name" }
}

$hasher = [System.Security.Cryptography.SHA256]::Create()
try { $hash = $hasher.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($configPath)) } finally { $hasher.Dispose() }
$hashText = ([System.BitConverter]::ToString($hash)).Replace("-", "")
$mutexName = "Global\CodexThreadRag-" + $hashText.Substring(0, 20)
$mutex = [System.Threading.Mutex]::new($false, $mutexName)
$hasMutex = $false
$run = [ordered]@{
  StartedAt = (Get-Date).ToUniversalTime().ToString("o")
  Config = $configPath
  Device = $settings.Device
  Profile = $settings.Profile
  NotebookId = $settings.NotebookId
  DryRun = [bool]$DryRun
  ReconcileOnly = [bool]$ReconcileOnly
  Steps = @()
  Status = "running"
}

try {
  $hasMutex = $mutex.WaitOne(0)
  if (-not $hasMutex) {
    $run.Status = "skipped-overlap"
    return
  }

  $root = [string]$settings.ProjectionRoot
  $runsDir = Join-Path $root "runs"
  $runnerStatePath = Join-Path $root "runner_state.json"
  $runnerState = if (Test-Path -LiteralPath $runnerStatePath) { Get-Content -Raw -LiteralPath $runnerStatePath | ConvertFrom-Json } else { [pscustomobject]@{} }

  if ($settings.RefreshMasterToken -ne $false) {
    $run.Steps += Invoke-Checked -Executable ([string]$settings.NotebookLmCli) -Arguments @("-p", [string]$settings.Profile, "login", "--master-token-refresh") -Label "auth-refresh"
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
    foreach ($threadId in @($settings.ThreadIds)) { $projectionArgs += @("--thread", [string]$threadId) }
    if ($DryRun) { $projectionArgs += "--dry-run" }
    $run.Steps += Invoke-Checked -Executable ([string]$settings.NodePath) -Arguments $projectionArgs -Label "projection"

    $syncArgs = @(
      [string]$settings.SyncScript,
      "--state", (Join-Path $root "state.json"),
      "--profile", [string]$settings.Profile,
      "--notebook-id", [string]$settings.NotebookId,
      "--wait-timeout", [string]$settings.WaitTimeout
    )
    if ($settings.SwapOld -ne $false) { $syncArgs += "--swap-old" }
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
    $run.Steps += Invoke-Checked -Executable ([string]$settings.PythonPath) -Arguments $validateArgs -Label "nightly-reconcile"
    $runnerState | Add-Member -NotePropertyName LastReconcileDate -NotePropertyValue $today -Force
    $runnerState | Add-Member -NotePropertyName LastReconcileAt -NotePropertyValue ((Get-Date).ToUniversalTime().ToString("o")) -Force
  }

  $runnerState | Add-Member -NotePropertyName LastSuccessAt -NotePropertyValue ((Get-Date).ToUniversalTime().ToString("o")) -Force
  Write-AtomicJson -Path $runnerStatePath -Value $runnerState
  $run.Status = "ok"
} catch {
  $run.Status = "error"
  $run.Error = "$($_.Exception.GetType().Name): $($_.Exception.Message)"
  throw
} finally {
  $run.CompletedAt = (Get-Date).ToUniversalTime().ToString("o")
  $runsDir = Join-Path ([string]$settings.ProjectionRoot) "runs"
  $runPath = Join-Path $runsDir ("runner-{0}.json" -f (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ"))
  Write-AtomicJson -Path $runPath -Value $run
  if ($hasMutex) { $mutex.ReleaseMutex() }
  $mutex.Dispose()
  [pscustomobject]@{ Status = $run.Status; Run = $runPath } | ConvertTo-Json
}
