param(
  [string] $CodexRoot = (Join-Path $env:USERPROFILE ".codex"),
  [string] $Python = "3.12",
  [switch] $CheckOnly,
  [switch] $SkipTests,
  [switch] $SkipSkill,
  [switch] $ForceSkill
)

$ErrorActionPreference = "Stop"
$repositoryFiles = @(
  "pyproject.toml",
  "uv.lock",
  "Install-CodexSkill.ps1",
  "tests\run_all.ps1",
  "skill\codex-notebooklm-thread-rag\SKILL.md"
)

function Get-RequiredTool {
  param(
    [Parameter(Mandatory = $true)] [string] $Name,
    [Parameter(Mandatory = $true)] [string] $InstallUrl
  )

  $command = Get-Command $Name -ErrorAction SilentlyContinue
  if (-not $command) {
    throw "$Name is required. Install it from $InstallUrl, then rerun this script."
  }
  $path = if ($command.Path) { $command.Path } else { $command.Source }
  $versionOutput = @(& $path --version 2>&1)
  $versionExitCode = $LASTEXITCODE
  $version = ($versionOutput | Select-Object -First 1 | Out-String).Trim()
  if ($versionExitCode -ne 0 -or -not $version) {
    throw "Unable to execute $Name at $path. Install or repair it, then rerun this script."
  }
  [pscustomobject]@{
    Name = $Name
    Path = $path
    Version = $version
  }
}

function Invoke-Preflight {
  foreach ($relativePath in $repositoryFiles) {
    $path = Join-Path $PSScriptRoot $relativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
      throw "Repository checkout is incomplete: missing $relativePath"
    }
  }

  $uvInfo = Get-RequiredTool -Name "uv" -InstallUrl "https://docs.astral.sh/uv/getting-started/installation/"
  $nodeInfo = Get-RequiredTool -Name "node" -InstallUrl "https://nodejs.org/"
  [pscustomobject]@{
    Repository = $PSScriptRoot
    PowerShell = $PSVersionTable.PSVersion.ToString()
    PythonSpec = $Python
    Tools = @($uvInfo, $nodeInfo)
    RequiredFiles = $repositoryFiles
  }
}

$preflight = Invoke-Preflight
$runtime = Join-Path $CodexRoot "runtimes\notebooklm-py-0.8.0"
$pythonExe = Join-Path $runtime "Scripts\python.exe"
$notebookLmExe = Join-Path $runtime "Scripts\notebooklm.exe"
$notebookLmMcpExe = Join-Path $runtime "Scripts\notebooklm-mcp.exe"
$uv = $preflight.Tools | Where-Object Name -eq "uv" | Select-Object -First 1
$node = $preflight.Tools | Where-Object Name -eq "node" | Select-Object -First 1

if ($CheckOnly) {
  [pscustomobject]@{
    Status = "ready"
    Preflight = $preflight
    Runtime = $runtime
    Next = "Run .\install.ps1 to create the isolated runtime and install the global Codex skill."
  } | ConvertTo-Json -Depth 6
  exit 0
}

if (-not (Test-Path -LiteralPath $pythonExe)) {
  & $uv.Path venv $runtime --python $Python
  if ($LASTEXITCODE -ne 0) { throw "uv venv failed with code $LASTEXITCODE" }
}
$lockExport = Join-Path ([System.IO.Path]::GetTempPath()) ("thread-rag-lock-{0}-{1}.txt" -f $PID, [guid]::NewGuid().ToString("N"))
try {
  & $uv.Path --quiet export --project $PSScriptRoot --locked --no-default-groups --no-emit-project --format requirements.txt --output-file $lockExport
  if ($LASTEXITCODE -ne 0) { throw "Locked dependency export failed with code $LASTEXITCODE" }
  & $uv.Path pip sync --python $pythonExe $lockExport
  if ($LASTEXITCODE -ne 0) { throw "Locked dependency synchronization failed with code $LASTEXITCODE" }
} finally {
  if (Test-Path -LiteralPath $lockExport) { Remove-Item -LiteralPath $lockExport -Force }
}
if (-not (Test-Path -LiteralPath $notebookLmExe)) { throw "NotebookLM CLI was not installed at $notebookLmExe" }
if (-not (Test-Path -LiteralPath $notebookLmMcpExe)) { throw "NotebookLM MCP server was not installed at $notebookLmMcpExe" }

if (-not $SkipTests) {
  & (Join-Path $PSScriptRoot "tests\run_all.ps1") -PythonPath $pythonExe -NodePath $node.Path | Out-Null
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
  NotebookLmMcp = $notebookLmMcpExe
  Upstream = "https://github.com/teng-lin/notebooklm-py"
  UpstreamVersion = "0.8.0"
  Skill = if ($skillResult) { $skillResult.Target } else { $null }
  TestsRun = -not $SkipTests
  Next = "Authenticate a profile, create a bounded test notebook, then run New-SyncConfig.ps1."
} | ConvertTo-Json -Depth 6
