param(
  [string] $PythonPath,
  [string] $NodePath = "node"
)

$ErrorActionPreference = "Stop"
$repository = Split-Path -Parent $PSScriptRoot
$pinnedPython = Join-Path ([Environment]::GetFolderPath("UserProfile")) ".codex\runtimes\notebooklm-py-0.8.0\Scripts\python.exe"
if (-not $PythonPath) { $PythonPath = if (Test-Path -LiteralPath $pinnedPython) { $pinnedPython } else { "python" } }
$steps = @()

function Invoke-Step {
  param([string] $Name, [scriptblock] $Action)
  $started = Get-Date
  $global:LASTEXITCODE = 0
  & $Action
  if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "$Name failed with code $LASTEXITCODE" }
  $script:steps += [pscustomobject]@{ Name = $Name; Passed = $true; DurationMs = [math]::Round(((Get-Date) - $started).TotalMilliseconds) }
}

$nodeTests = @(Get-ChildItem -Recurse -File -LiteralPath $repository | Where-Object { $_.Name -like "*.test.mjs" } | ForEach-Object FullName)
Invoke-Step "node-tests" { & $NodePath --test @nodeTests }
Invoke-Step "python-tests" { & $PythonPath -m unittest discover -s (Join-Path $repository "tests") -p "test_*.py" -v }
$pythonScripts = @(Get-ChildItem -File -LiteralPath (Join-Path $repository "scripts") | Where-Object { $_.Extension -in @(".py", ".pyw") } | ForEach-Object FullName)
Invoke-Step "python-compile" { & $PythonPath -m py_compile @pythonScripts }

$parseTargets = @(
  (Join-Path $repository "install.ps1"),
  (Join-Path $repository "Install-CodexSkill.ps1"),
  (Join-Path $repository "New-SyncConfig.ps1")
) + @(Get-ChildItem -File -LiteralPath (Join-Path $repository "scripts") -Filter "*.ps1" | ForEach-Object FullName)
foreach ($path in $parseTargets) {
  $tokens = $null
  $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors) | Out-Null
  if ($errors.Count) { throw "PowerShell parse failed for $path`: $($errors[0].Message)" }
}
$steps += [pscustomobject]@{ Name = "powershell-parse"; Passed = $true; DurationMs = 0 }

Invoke-Step "runner-integration" { & (Join-Path $repository "tests\runner.integration.ps1") -Runner (Join-Path $repository "scripts\notebooklm_thread_sync_runner.ps1") | Out-Null }
Invoke-Step "doctor-integration" { & (Join-Path $repository "tests\doctor.integration.ps1") -Doctor (Join-Path $repository "scripts\thread_rag_doctor.ps1") | Out-Null }
Invoke-Step "profile-auth-integration" { & (Join-Path $repository "tests\profile_auth.integration.ps1") -ProfileScript (Join-Path $repository "scripts\notebooklm_profiles.ps1") | Out-Null }
Invoke-Step "profile-acl-integration" { & (Join-Path $repository "tests\profile_acl.integration.ps1") -ProfileScript (Join-Path $repository "scripts\notebooklm_profiles.ps1") | Out-Null }
Invoke-Step "skill-install-integration" { & (Join-Path $repository "tests\install_skill.integration.ps1") -RepositoryRoot $repository | Out-Null }
Invoke-Step "config-integration" { & (Join-Path $repository "tests\config.integration.ps1") -RepositoryRoot $repository | Out-Null }
Invoke-Step "task-scheduler-integration" { & (Join-Path $repository "tests\task_scheduler.integration.ps1") -RepositoryRoot $repository -PythonPath $PythonPath | Out-Null }

[pscustomobject]@{ Status = "passed"; TestFiles = $nodeTests.Count; PythonScripts = $pythonScripts.Count; Steps = $steps } | ConvertTo-Json -Depth 6
