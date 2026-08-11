param(
  [Parameter(Mandatory = $true)] [string] $RepositoryRoot,
  [Parameter(Mandatory = $true)] [string] $PythonPath
)

$ErrorActionPreference = "Stop"
function Assert-True { param([bool] $Condition, [string] $Message) if (-not $Condition) { throw "Assertion failed: $Message" } }

$temporary = Join-Path ([System.IO.Path]::GetTempPath()) ("thread-rag-scheduler-test-" + [guid]::NewGuid().ToString("N"))
try {
  New-Item -ItemType Directory -Path $temporary -Force | Out-Null
  $config = Join-Path $temporary "sync_config.json"
  $marker = Join-Path $temporary "runner.marker"
  $fakeRunner = Join-Path $temporary "fake_runner.ps1"
  [pscustomobject]@{
    PythonPath = $PythonPath
    ExecutionTimeLimitMinutes = 120
    Marker = $marker
    ExitCode = 0
  } | ConvertTo-Json | Set-Content -LiteralPath $config -Encoding UTF8
  @'
param([Parameter(Mandatory = $true)] [string] $Config)
$settings = Get-Content -Raw -LiteralPath $Config | ConvertFrom-Json
Set-Content -LiteralPath ([string]$settings.Marker) -Value $Config -Encoding UTF8
exit ([int]$settings.ExitCode)
'@ | Set-Content -LiteralPath $fakeRunner -Encoding UTF8

  $installer = Join-Path $RepositoryRoot "scripts\install_notebooklm_thread_sync_task.ps1"
  $plan = (& $installer -Config $config -TaskName "Thread RAG scheduler integration test" -PlanOnly) | ConvertFrom-Json
  Assert-True ($plan.Status -eq "planned") "plan-only mode must not register a task"
  Assert-True ($plan.LaunchMode -eq "pythonw-create-no-window") "installer must select the console-free launch mode"
  Assert-True ((Split-Path -Leaf ([string]$plan.ActionExecutable)) -like "pythonw*.exe") "scheduled action must use pythonw"
  Assert-True ([string]$plan.ActionArguments -like "*$([string]$plan.Launcher)*") "scheduled arguments must include the hidden launcher"
  Assert-True ([string]$plan.ActionArguments -like "*$config*") "scheduled arguments must include the exact config"
  Assert-True ([string]$plan.ActionExecutable -notlike "*powershell.exe") "PowerShell must not be the visible top-level task action"

  $powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
  $hiddenArguments = @([string]$plan.Launcher, $powershell, $fakeRunner, $config) | ForEach-Object { '"' + $_ + '"' }
  $hiddenArguments = $hiddenArguments -join ' '
  $missingPowerShell = Join-Path $temporary "missing-powershell.exe"
  $badArguments = @([string]$plan.Launcher, $missingPowerShell, $fakeRunner, $config) | ForEach-Object { '"' + $_ + '"' }
  $badArguments = $badArguments -join ' '
  $process = Start-Process -FilePath ([string]$plan.ActionExecutable) -ArgumentList $badArguments -Wait -PassThru
  $launchError = Join-Path $temporary "scheduler-launch-error.json"
  Assert-True ($process.ExitCode -eq 70) "launcher bootstrap failures must return the documented software error code"
  Assert-True (Test-Path -LiteralPath $launchError) "a hidden bootstrap failure must leave a bounded diagnostic"

  $process = Start-Process -FilePath ([string]$plan.ActionExecutable) -ArgumentList $hiddenArguments -Wait -PassThru
  Assert-True ($process.ExitCode -eq 0) "launcher must preserve a successful runner exit code"
  Assert-True (Test-Path -LiteralPath $marker) "launcher must execute the runner with the supplied config"
  Assert-True (-not (Test-Path -LiteralPath $launchError)) "a recovered launcher must clear its stale bootstrap error"

  $settings = Get-Content -Raw -LiteralPath $config | ConvertFrom-Json
  $settings.ExitCode = 23
  $settings | ConvertTo-Json | Set-Content -LiteralPath $config -Encoding UTF8
  $process = Start-Process -FilePath ([string]$plan.ActionExecutable) -ArgumentList $hiddenArguments -Wait -PassThru
  Assert-True ($process.ExitCode -eq 23) "launcher must preserve a failed runner exit code"

  [pscustomobject]@{ Status = "passed"; Checks = 12 } | ConvertTo-Json
} finally {
  if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
