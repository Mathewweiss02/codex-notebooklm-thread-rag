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
  Assert-True ($config.NotebookRole -eq "retrieval" -and $config.DisposableSearchChat -eq $true) "default config must isolate disposable retrieval chat"
  Assert-True ($config.AutoEnroll -eq $true -and $config.SourceReserve -ge 1) "default config must enable capacity-aware enrollment"
  Assert-True ([string]$config.SoakEvidenceRoot -like "$temporary\thread-rag\fixture\soak-evidence") "config must place protected soak evidence under the projection root"
  Assert-True ($config.ExecutionTimeLimitMinutes -ge 120) "scheduler budget must cover long initial uploads"
  Assert-True ($config.TemporalRefresh -eq $true -and [string]$config.TemporalRefreshScript -and [string]$config.TemporalIndexScript) "retrieval config must refresh temporal memory"
  Assert-True ([string]$config.ProjectionScript -like "$temporary\skills\codex-notebooklm-thread-rag\scripts\*") "config must use globally installed skill scripts"
  $registry = Get-Content -Raw -LiteralPath (Join-Path $temporary "thread-rag\registry.json") | ConvertFrom-Json
  Assert-True (@($registry.Configs).Count -eq 1) "config must register exactly once"
  & $generator -CodexRoot $temporary -Device "fixture" -NotebookId "notebook" -Profile personal -ThreadIds @("thread-a") | Out-Null
  $registry = Get-Content -Raw -LiteralPath (Join-Path $temporary "thread-rag\registry.json") | ConvertFrom-Json
  Assert-True (@($registry.Configs).Count -eq 1) "regeneration must update instead of duplicating registry entries"
  $chatOutput = Join-Path $temporary "chat-config.json"
  & $generator -CodexRoot $temporary -Device "fixture-chat" -NotebookId "chat-notebook" -Profile personal -NotebookRole chat -ThreadIds @("thread-a") -Output $chatOutput | Out-Null
  $chat = Get-Content -Raw -LiteralPath $chatOutput | ConvertFrom-Json
  Assert-True ($chat.NotebookRole -eq "chat" -and $chat.DisposableSearchChat -eq $false) "CLI chat config must preserve conversation history"
  Assert-True ($chat.TemporalRefresh -eq $false) "CLI chat config must not own the shared temporal refresh"
  [pscustomobject]@{ Status = "passed"; Checks = 10 } | ConvertTo-Json
} finally {
  if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
