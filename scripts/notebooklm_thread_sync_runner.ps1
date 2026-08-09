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
$isSharded = $settings.Sharded -eq $true
$required = @("Device", "ProjectionRoot", "Profile", "NodePath", "PythonPath", "NotebookLmCli", "ProjectionScript", "SyncScript")
if ($isSharded) {
  $required += @("PlanScript", "SourceLimit", "Reserve", "ShardPrefix")
} else {
  $required += "NotebookId"
}
foreach ($name in $required) {
  if (-not $settings.$name) { throw "Missing required config field: $name" }
}
$threadIds = @($settings.ThreadIds | Where-Object { $_ })
if ($threadIds.Count -eq 0 -and $settings.AllowAllThreads -ne $true) {
  throw "ThreadIds is empty. Set AllowAllThreads=true explicitly only after source-budget planning."
}

$mutexScope = [System.IO.Path]::GetFullPath([string]$settings.ProjectionRoot).ToLowerInvariant()
$hasher = [System.Security.Cryptography.SHA256]::Create()
try { $hash = $hasher.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($mutexScope)) } finally { $hasher.Dispose() }
$hashText = ([System.BitConverter]::ToString($hash)).Replace("-", "")
$mutexName = "Global\CodexThreadRag-" + $hashText.Substring(0, 20)
$mutex = [System.Threading.Mutex]::new($false, $mutexName)
$hasMutex = $false
$run = [ordered]@{
  StartedAt = (Get-Date).ToUniversalTime().ToString("o")
  Config = $configPath
  Device = $settings.Device
  Profile = $settings.Profile
  Sharded = $isSharded
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
    foreach ($threadId in $threadIds) { $projectionArgs += @("--thread", [string]$threadId) }
    if ($DryRun) { $projectionArgs += "--dry-run" }
    $run.Steps += Invoke-Checked -Executable ([string]$settings.NodePath) -Arguments $projectionArgs -Label "projection"

    if ($isSharded) {
      $planPath = if ($settings.ShardPlanPath) { [string]$settings.ShardPlanPath } else { Join-Path $root "shard_plan.json" }
      $planArgs = @(
        [string]$settings.PlanScript,
        "--state", (Join-Path $root "state.json"),
        "--source-limit", [string]$settings.SourceLimit,
        "--reserve", [string]$settings.Reserve,
        "--prefix", [string]$settings.ShardPrefix,
        "--out", $planPath
      )
      $run.Steps += Invoke-Checked -Executable ([string]$settings.PythonPath) -Arguments $planArgs -Label "shard-plan"
      $plan = Get-Content -Raw -LiteralPath $planPath | ConvertFrom-Json
      $shards = @($plan.shards)
      if ($shards.Count -eq 0 -and $plan.threadCount -gt 0) { throw "Shard plan contains tasks but no shards." }
      foreach ($shard in $shards) {
        $shardThreads = @($shard.threads | ForEach-Object { [string]$_.threadId } | Where-Object { $_ })
        if (-not $shard.notebookId) {
          throw "Shard $($shard.index) has no provisioned NotebookLM notebook. Provision one and rerun; no tasks were dropped."
        }
        if ($shardThreads.Count -eq 0) { continue }
        $syncArgs = @(
          [string]$settings.SyncScript,
          "--state", (Join-Path $root "state.json"),
          "--profile", [string]$settings.Profile,
          "--notebook-id", [string]$shard.notebookId,
          "--wait-timeout", [string]$settings.WaitTimeout
        )
        foreach ($threadId in $shardThreads) { $syncArgs += @("--thread", $threadId) }
        if ($settings.SwapOld -ne $false) { $syncArgs += "--swap-old" }
        if ($DryRun) { $syncArgs += "--dry-run" }
        $run.Steps += Invoke-Checked -Executable ([string]$settings.PythonPath) -Arguments $syncArgs -Label ("sync-shard-{0}" -f $shard.index)
      }
      $run.ShardCount = $shards.Count
      $run.ThreadCount = [int]$plan.threadCount
      $run.SourceParts = [int]$plan.sourceParts
    } else {
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
  }

  if (($ReconcileOnly -or $isReconcileDue) -and -not $DryRun) {
    if ($isSharded) {
      $planPath = if ($settings.ShardPlanPath) { [string]$settings.ShardPlanPath } else { Join-Path $root "shard_plan.json" }
      $plan = Get-Content -Raw -LiteralPath $planPath | ConvertFrom-Json
      foreach ($shard in @($plan.shards)) {
        $shardThreads = @($shard.threads | ForEach-Object { [string]$_.threadId } | Where-Object { $_ })
        if (-not $shard.notebookId) { throw "Shard $($shard.index) has no provisioned NotebookLM notebook." }
        $validateArgs = @(
          [string]$settings.SyncScript,
          "--state", (Join-Path $root "state.json"),
          "--profile", [string]$settings.Profile,
          "--notebook-id", [string]$shard.notebookId,
          "--validate-only"
        )
        foreach ($threadId in $shardThreads) { $validateArgs += @("--thread", $threadId) }
        $run.Steps += Invoke-Checked -Executable ([string]$settings.PythonPath) -Arguments $validateArgs -Label ("nightly-reconcile-shard-{0}" -f $shard.index)
      }
    } else {
      $validateArgs = @(
        [string]$settings.SyncScript,
        "--state", (Join-Path $root "state.json"),
        "--profile", [string]$settings.Profile,
        "--notebook-id", [string]$settings.NotebookId,
        "--validate-only"
      )
      $run.Steps += Invoke-Checked -Executable ([string]$settings.PythonPath) -Arguments $validateArgs -Label "nightly-reconcile"
    }
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
  $runPath = Join-Path $runsDir ("runner-{0}-{1}.json" -f (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffZ"), $PID)
  Write-AtomicJson -Path $runPath -Value $run
  if ($hasMutex) { $mutex.ReleaseMutex() }
  $mutex.Dispose()
  [pscustomobject]@{ Status = $run.Status; Run = $runPath } | ConvertTo-Json
}
