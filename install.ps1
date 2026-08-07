param(
  [string] $CodexRoot = (Join-Path $env:USERPROFILE ".codex"),
  [string] $Python = "3.12",
  [switch] $SkipTests
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
  & $node.Source --test (Join-Path $PSScriptRoot "scripts\notebooklm_thread_projection.test.mjs")
  if ($LASTEXITCODE -ne 0) { throw "Projection tests failed with code $LASTEXITCODE" }
  & $pythonExe -m py_compile (Join-Path $PSScriptRoot "scripts\notebooklm_thread_sync.py") (Join-Path $PSScriptRoot "scripts\notebooklm_thread_retrieval_benchmark.py")
  if ($LASTEXITCODE -ne 0) { throw "Python compilation failed with code $LASTEXITCODE" }
}

[pscustomobject]@{
  Status = "installed"
  Runtime = $runtime
  Python = $pythonExe
  NotebookLm = $notebookLmExe
  Next = "Authenticate a profile, create a test notebook, then generate config.local.json."
} | ConvertTo-Json
