param(
  [Parameter(Mandatory = $true)] [string] $RepositoryRoot
)

$ErrorActionPreference = "Stop"
function Assert-True { param([bool] $Condition, [string] $Message) if (-not $Condition) { throw "Assertion failed: $Message" } }

$temporary = Join-Path ([System.IO.Path]::GetTempPath()) ("thread-rag-skill-test-" + [guid]::NewGuid().ToString("N"))
try {
  $installer = Join-Path $RepositoryRoot "Install-CodexSkill.ps1"
  $first = (& $installer -CodexRoot $temporary) | ConvertFrom-Json
  Assert-True ($first.Status -eq "installed") "first skill install must succeed"
  $target = Join-Path $temporary "skills\codex-notebooklm-thread-rag"
  Assert-True (Test-Path -LiteralPath (Join-Path $target "SKILL.md")) "installed SKILL.md is required"
  Assert-True (Test-Path -LiteralPath (Join-Path $target "agents\openai.yaml")) "installed agent metadata is required"
  Assert-True (Test-Path -LiteralPath (Join-Path $target "scripts\notebooklm_thread_search.py")) "semantic search script is required"
  Assert-True (Test-Path -LiteralPath (Join-Path $target "scripts\thread_search.mjs")) "local fallback script is required"
  Assert-True (Test-Path -LiteralPath (Join-Path $target "scripts\redaction_contract.json")) "shared redaction contract is required"
  Assert-True (Test-Path -LiteralPath (Join-Path $target "scripts\notebooklm_thread_enroll.py")) "capacity-aware enrollment script is required"
  Assert-True (Test-Path -LiteralPath (Join-Path $target "scripts\thread_rag_retention.py")) "bounded retention script is required"
  Assert-True (Test-Path -LiteralPath (Join-Path $target "scripts\notebooklm_thread_sync_hidden.pyw")) "console-free scheduler launcher is required"

  $second = (& $installer -CodexRoot $temporary) | ConvertFrom-Json
  Assert-True ($second.Status -eq "installed") "upgrade install must succeed"
  Assert-True ([bool]$second.Backup) "upgrade install must retain a rollback backup"
  Assert-True (Test-Path -LiteralPath $second.Backup) "rollback backup must exist outside the skills scan root"
  Assert-True (Test-Path -LiteralPath (Join-Path $temporary "thread-rag\installation.json")) "installation manifest is required"
  [pscustomobject]@{ Status = "passed"; Checks = 11 } | ConvertTo-Json
} finally {
  if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
