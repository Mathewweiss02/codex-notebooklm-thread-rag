param(
  [string] $CodexRoot = (Join-Path $env:USERPROFILE ".codex"),
  [switch] $Force
)

$ErrorActionPreference = "Stop"
$skillName = "codex-notebooklm-thread-rag"
$source = Join-Path $PSScriptRoot "skill\$skillName"
$scriptsSource = Join-Path $PSScriptRoot "scripts"
$skillsRoot = Join-Path $CodexRoot "skills"
$target = Join-Path $skillsRoot $skillName
$stagingRoot = Join-Path $CodexRoot "skill-install-staging"
$stage = Join-Path $stagingRoot ("$skillName-$PID")
$backup = $null

if (-not (Test-Path -LiteralPath (Join-Path $source "SKILL.md"))) { throw "Bundled skill source is missing: $source" }
if (-not (Test-Path -LiteralPath $scriptsSource)) { throw "Bundled scripts are missing: $scriptsSource" }
if (Test-Path -LiteralPath $target) {
  $existingSkill = Join-Path $target "SKILL.md"
  $owned = (Test-Path -LiteralPath $existingSkill) -and [bool](Select-String -LiteralPath $existingSkill -Pattern '^name:\s*codex-notebooklm-thread-rag\s*$' -Quiet)
  if (-not $owned -and -not $Force) { throw "Refusing to replace an unrecognized skill at $target. Use -Force only after reviewing it." }
}

New-Item -ItemType Directory -Path $skillsRoot -Force | Out-Null
New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage -Force | Out-Null
Copy-Item -Path (Join-Path $source "*") -Destination $stage -Recurse -Force
New-Item -ItemType Directory -Path (Join-Path $stage "scripts") -Force | Out-Null
Copy-Item -Path (Join-Path $scriptsSource "*") -Destination (Join-Path $stage "scripts") -Recurse -Force
if (Test-Path -LiteralPath (Join-Path $stage "scripts\__pycache__")) { Remove-Item -LiteralPath (Join-Path $stage "scripts\__pycache__") -Recurse -Force }

$validator = Join-Path $CodexRoot "skills\.system\skill-creator\scripts\quick_validate.py"
if (Test-Path -LiteralPath $validator) {
  $python = Get-Command python -ErrorAction SilentlyContinue
  if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
  if ($python) {
    & $python.Source -X utf8 $validator $stage | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Bundled Codex skill validation failed with code $LASTEXITCODE" }
  }
}

try {
  if (Test-Path -LiteralPath $target) {
    $backupRoot = Join-Path $CodexRoot "skill-backups"
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    $backup = Join-Path $backupRoot ("{0}-{1}" -f $skillName, (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ"))
    Move-Item -LiteralPath $target -Destination $backup
  }
  Move-Item -LiteralPath $stage -Destination $target
} catch {
  if (-not (Test-Path -LiteralPath $target) -and $backup -and (Test-Path -LiteralPath $backup)) {
    Move-Item -LiteralPath $backup -Destination $target
  }
  throw
}

$installStateDir = Join-Path $CodexRoot "thread-rag"
New-Item -ItemType Directory -Path $installStateDir -Force | Out-Null
$manifest = [ordered]@{
  SchemaVersion = 1
  Skill = $skillName
  InstalledAt = (Get-Date).ToUniversalTime().ToString("o")
  Target = $target
  SourceRepository = $PSScriptRoot
  Backup = $backup
}
$manifestPath = Join-Path $installStateDir "installation.json"
$temporary = "$manifestPath.$PID.tmp"
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $temporary -Encoding UTF8
Move-Item -LiteralPath $temporary -Destination $manifestPath -Force
[pscustomobject]@{ Status = "installed"; Target = $target; Backup = $backup; Manifest = $manifestPath } | ConvertTo-Json
