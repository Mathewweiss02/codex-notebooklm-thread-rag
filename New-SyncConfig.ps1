param(
  [Parameter(Mandatory = $true)] [string] $Device,
  [string] $NotebookId,
  [switch] $Sharded,
  [ValidateRange(1, 1000)] [int] $SourceLimit = 300,
  [ValidateRange(1, 999)] [int] $Reserve = 60,
  [string] $ShardPrefix,
  [ValidateSet("work", "personal")] [string] $Profile = "personal",
  [string] $CodexRoot = (Join-Path $env:USERPROFILE ".codex"),
  [string] $Output,
  [string[]] $ThreadIds = @(),
  [switch] $AllowAllThreads,
  [bool] $Register = $true
)

$ErrorActionPreference = "Stop"
$runtime = Join-Path $CodexRoot "runtimes\notebooklm-py-0.8.0"
$cleanThreadIds = @($ThreadIds | Where-Object { $_ })
if ($cleanThreadIds.Count -eq 0 -and -not $AllowAllThreads) {
  throw "Provide at least one -ThreadIds value. Use -AllowAllThreads only after running the source-budget planner."
}
if (-not $Sharded -and -not $NotebookId) { throw "NotebookId is required unless -Sharded is used." }
if ($Reserve -ge $SourceLimit) { throw "Reserve must be smaller than SourceLimit." }
$node = (Get-Command node -ErrorAction Stop).Source
$projectionRoot = Join-Path $CodexRoot ("thread-rag\" + $Device)
if (-not $Output) { $Output = Join-Path $projectionRoot "sync_config.json" }
$installedScripts = Join-Path $CodexRoot "skills\codex-notebooklm-thread-rag\scripts"
$scriptRoot = if (Test-Path -LiteralPath (Join-Path $installedScripts "notebooklm_thread_projection.mjs")) { $installedScripts } else { Join-Path $PSScriptRoot "scripts" }
$config = [ordered]@{
  Device = $Device
  ProjectionRoot = $projectionRoot
  Profile = $Profile
  Sharded = [bool]$Sharded
  NodePath = $node
  PythonPath = Join-Path $runtime "Scripts\python.exe"
  NotebookLmCli = Join-Path $runtime "Scripts\notebooklm.exe"
  ProjectionScript = Join-Path $scriptRoot "notebooklm_thread_projection.mjs"
  PlanScript = Join-Path $scriptRoot "notebooklm_thread_plan.py"
  SyncScript = Join-Path $scriptRoot "notebooklm_thread_sync.py"
  ShardPlanPath = Join-Path $projectionRoot "shard_plan.json"
  SourceLimit = $SourceLimit
  Reserve = $Reserve
  ShardPrefix = $(if ($ShardPrefix) { $ShardPrefix } else { "Codex Threads - $Device" })
  QuietMinutes = 60
  HardMaxHours = 6
  MaxWords = 120000
  MaxMessageChars = 100000
  MaxLineBytes = 4194304
  WaitTimeout = 300
  RefreshMasterToken = $true
  SwapOld = $true
  ReconcileHour = 3
  AllowAllThreads = [bool]$AllowAllThreads
  DisposableSearchChat = $true
  ThreadIds = $cleanThreadIds
}
if (-not $Sharded) { $config["NotebookId"] = $NotebookId }
$outputParent = Split-Path -Parent $Output
if ($outputParent) { New-Item -ItemType Directory -Path $outputParent -Force | Out-Null }
$config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Output -Encoding UTF8
$resolvedOutput = (Resolve-Path -LiteralPath $Output).Path
if ($Register) {
  $registryPath = Join-Path (Join-Path $CodexRoot "thread-rag") "registry.json"
  $registry = if (Test-Path -LiteralPath $registryPath) { Get-Content -Raw -LiteralPath $registryPath | ConvertFrom-Json } else { [pscustomobject]@{ SchemaVersion = 1; Configs = @() } }
  $entries = @($registry.Configs | Where-Object { [string]$_.Device -ne $Device -and [string]$_.ConfigPath -ne $resolvedOutput })
  $entries += [pscustomobject]@{ Device = $Device; ConfigPath = $resolvedOutput; Profile = $Profile; UpdatedAt = (Get-Date).ToUniversalTime().ToString("o") }
  $registry = [ordered]@{ SchemaVersion = 1; Configs = $entries }
  $registryTemporary = "$registryPath.$PID.tmp"
  $registry | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $registryTemporary -Encoding UTF8
  Move-Item -LiteralPath $registryTemporary -Destination $registryPath -Force
}
[pscustomobject]@{ Status = "created"; Config = $resolvedOutput; Registered = $Register; ScriptRoot = $scriptRoot } | ConvertTo-Json
