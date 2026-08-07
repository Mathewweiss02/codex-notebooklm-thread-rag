param(
  [Parameter(Mandatory = $true)] [string] $Device,
  [Parameter(Mandatory = $true)] [string] $NotebookId,
  [ValidateSet("work", "personal")] [string] $Profile = "personal",
  [string] $CodexRoot = (Join-Path $env:USERPROFILE ".codex"),
  [string] $Output = (Join-Path $PSScriptRoot "config.local.json"),
  [string[]] $ThreadIds = @()
)

$ErrorActionPreference = "Stop"
$runtime = Join-Path $CodexRoot "runtimes\notebooklm-py-0.8.0"
$node = (Get-Command node -ErrorAction Stop).Source
$config = [ordered]@{
  Device = $Device
  ProjectionRoot = Join-Path $CodexRoot ("thread-rag\" + $Device)
  Profile = $Profile
  NotebookId = $NotebookId
  NodePath = $node
  PythonPath = Join-Path $runtime "Scripts\python.exe"
  NotebookLmCli = Join-Path $runtime "Scripts\notebooklm.exe"
  ProjectionScript = Join-Path $PSScriptRoot "scripts\notebooklm_thread_projection.mjs"
  SyncScript = Join-Path $PSScriptRoot "scripts\notebooklm_thread_sync.py"
  QuietMinutes = 60
  HardMaxHours = 6
  MaxWords = 120000
  MaxMessageChars = 100000
  MaxLineBytes = 4194304
  WaitTimeout = 300
  RefreshMasterToken = $true
  SwapOld = $true
  ReconcileHour = 3
  ThreadIds = @($ThreadIds)
}
$config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Output -Encoding UTF8
[pscustomobject]@{ Status = "created"; Config = (Resolve-Path -LiteralPath $Output).Path } | ConvertTo-Json
