param(
  [Parameter(Mandatory = $true)] [string] $RepositoryRoot
)

$ErrorActionPreference = "Stop"
function Assert-True { param([bool] $Condition, [string] $Message) if (-not $Condition) { throw "Assertion failed: $Message" } }

$temporary = Join-Path ([System.IO.Path]::GetTempPath()) ("thread-rag-config-test-" + [guid]::NewGuid().ToString("N"))
try {
  & (Join-Path $RepositoryRoot "Install-CodexSkill.ps1") -CodexRoot $temporary | Out-Null
  $generator = Join-Path $RepositoryRoot "New-SyncConfig.ps1"
  $unsafeFailed = $false
  try { & $generator -CodexRoot $temporary -Device "fixture" -NotebookId "notebook" -Profile personal | Out-Null } catch { $unsafeFailed = $_.Exception.Message -match "AllowAllThreads" }
  Assert-True $unsafeFailed "empty ThreadIds must be rejected by default"

  $result = (& $generator -CodexRoot $temporary -Device "fixture" -NotebookId "notebook" -Profile personal -ThreadIds @("thread-a", "thread-b")) | ConvertFrom-Json
  Assert-True (Test-Path -LiteralPath $result.Config) "config must be created under stable Codex state"
  $config = Get-Content -Raw -LiteralPath $result.Config | ConvertFrom-Json
  Assert-True ($config.ThreadIds.Count -eq 2) "thread scope must be preserved"
  Assert-True ([string]$config.ProjectionScript -like "$temporary\skills\codex-notebooklm-thread-rag\scripts\*") "config must use globally installed skill scripts"
  $registry = Get-Content -Raw -LiteralPath (Join-Path $temporary "thread-rag\registry.json") | ConvertFrom-Json
  Assert-True (@($registry.Configs).Count -eq 1) "config must register exactly once"
  & $generator -CodexRoot $temporary -Device "fixture" -NotebookId "notebook" -Profile personal -ThreadIds @("thread-a") | Out-Null
  $registry = Get-Content -Raw -LiteralPath (Join-Path $temporary "thread-rag\registry.json") | ConvertFrom-Json
  Assert-True (@($registry.Configs).Count -eq 1) "regeneration must update instead of duplicating registry entries"

  $shardedOutput = Join-Path $temporary "sharded.json"
  & $generator -CodexRoot $temporary -Device "fixture-sharded" -Profile personal -AllowAllThreads -Sharded -Output $shardedOutput -Register:$false | Out-Null
  $sharded = Get-Content -Raw -LiteralPath $shardedOutput | ConvertFrom-Json
  Assert-True ($sharded.Sharded -eq $true) "sharded config must be explicit"
  Assert-True (-not $sharded.NotebookId) "sharded config must not require a single notebook"
  Assert-True ([bool]$sharded.PlanScript) "sharded config must include the planner"
  [pscustomobject]@{ Status = "passed"; Checks = 9 } | ConvertTo-Json
} finally {
  if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
