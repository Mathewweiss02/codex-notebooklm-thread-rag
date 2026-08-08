param(
  [string] $CodexRoot = (Join-Path $env:USERPROFILE ".codex"),
  [string] $Python = "3.12",
  [switch] $SkipTests,
  [switch] $SkipSkill,
  [switch] $ForceSkill
)

$ErrorActionPreference = "Stop"
$runtime = Join-Path $CodexRoot "runtimes\notebooklm-py-0.8.0"
$pythonExe = Join-Path $runtime "Scripts\python.exe"
$notebookLmExe = Join-Path $runtime "Scripts\notebooklm.exe"
$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) { throw "uv is required. Install uv, then rerun this script." }
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) { throw "Node.js is required to project Codex JSONL sessions." }

if (-not (Test-Path -LiteralPath $pythonExe)) {
  & $uv.Source venv $runtime --python $Python
  if ($LASTEXITCODE -ne 0) { throw "uv venv failed with code $LASTEXITCODE" }
}
& $uv.Source pip install --python $pythonExe -r (Join-Path $PSScriptRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed with code $LASTEXITCODE" }

if (-not $SkipTests) {
  & (Join-Path $PSScriptRoot "tests\run_all.ps1") -PythonPath $pythonExe -NodePath $node.Source | Out-Null
}

$skillResult = $null
if (-not $SkipSkill) {
  $skillArgs = @{ CodexRoot = $CodexRoot }
  if ($ForceSkill) { $skillArgs.Force = $true }
  $skillResult = & (Join-Path $PSScriptRoot "Install-CodexSkill.ps1") @skillArgs | ConvertFrom-Json
}

[pscustomobject]@{
  Status = "installed"
  Runtime = $runtime
  Python = $pythonExe
  NotebookLm = $notebookLmExe
  Skill = $skillResult.Target
  Next = "Authenticate a profile, create a bounded test notebook, then run New-SyncConfig.ps1."
} | ConvertTo-Json
