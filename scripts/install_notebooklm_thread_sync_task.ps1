param(
  [Parameter(Mandatory = $true)]
  [string] $Config,
  [string] $TaskName = "Codex NotebookLM Thread Sync",
  [ValidateRange(10, 1440)]
  [int] $Minutes = 15,
  [ValidateRange(0, 1440)]
  [int] $ExecutionTimeLimitMinutes = 0,
  [switch] $PlanOnly,
  [switch] $Remove
)

$ErrorActionPreference = "Stop"
if ($PlanOnly -and $Remove) { throw "PlanOnly and Remove cannot be used together." }

function Resolve-ExecutablePath {
  param(
    [Parameter(Mandatory = $true)] [string] $Value,
    [Parameter(Mandatory = $true)] [string] $Label
  )
  $expanded = [Environment]::ExpandEnvironmentVariables($Value)
  if (Test-Path -LiteralPath $expanded -PathType Leaf) { return (Resolve-Path -LiteralPath $expanded).Path }
  $command = Get-Command $expanded -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($command -and $command.Source) { return [string]$command.Source }
  throw "$Label executable not found: $Value"
}

function Quote-TaskArgument {
  param([Parameter(Mandatory = $true)] [string] $Value)
  if ($Value.Contains('"')) { throw "Scheduled-task paths cannot contain a quote character: $Value" }
  return '"' + $Value + '"'
}

$configPath = (Resolve-Path -LiteralPath $Config).Path
$configSettings = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$effectiveExecutionLimit = if ($ExecutionTimeLimitMinutes -gt 0) { $ExecutionTimeLimitMinutes } elseif ($configSettings.ExecutionTimeLimitMinutes) { [int]$configSettings.ExecutionTimeLimitMinutes } else { 120 }
if ($effectiveExecutionLimit -lt 15) { throw "Execution time limit must be at least 15 minutes." }
$runner = Join-Path $PSScriptRoot "notebooklm_thread_sync_runner.ps1"
if (-not (Test-Path -LiteralPath $runner)) { throw "Runner not found: $runner" }

if ($Remove) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
  [pscustomobject]@{ TaskName = $TaskName; Status = "removed" } | ConvertTo-Json
  return
}

$principalName = "$env:USERDOMAIN\$env:USERNAME"
$launcher = Join-Path $PSScriptRoot "notebooklm_thread_sync_hidden.pyw"
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) { throw "Console-free task launcher not found: $launcher" }
if (-not $configSettings.PythonPath) { throw "Config is missing PythonPath, which is required for console-free scheduling." }
$python = Resolve-ExecutablePath -Value ([string]$configSettings.PythonPath) -Label "Configured Python"
$pythonDirectory = Split-Path -Parent $python
$pythonLeaf = Split-Path -Leaf $python
$pythonwLeaves = @(
  ($pythonLeaf -replace '^python', 'pythonw'),
  'pythonw.exe'
) | Select-Object -Unique
$pythonw = $null
foreach ($leaf in $pythonwLeaves) {
  $candidate = Join-Path $pythonDirectory $leaf
  if (Test-Path -LiteralPath $candidate -PathType Leaf) {
    $pythonw = (Resolve-Path -LiteralPath $candidate).Path
    break
  }
}
if (-not $pythonw) { throw "Console-free Python executable not found beside configured Python: $pythonDirectory" }
$powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
if (-not (Test-Path -LiteralPath $powershell -PathType Leaf)) { throw "Windows PowerShell executable not found: $powershell" }
$actionArguments = @($launcher, $powershell, $runner, $configPath) | ForEach-Object { Quote-TaskArgument -Value $_ }
$actionArguments = $actionArguments -join ' '
$action = New-ScheduledTaskAction -Execute $pythonw -Argument $actionArguments
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes $Minutes)
$principal = New-ScheduledTaskPrincipal -UserId $principalName -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes $effectiveExecutionLimit) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

if ($PlanOnly) {
  [pscustomobject]@{
    TaskName = $TaskName
    Status = "planned"
    IntervalMinutes = $Minutes
    ExecutionTimeLimitMinutes = $effectiveExecutionLimit
    Config = $configPath
    Runner = $runner
    Launcher = $launcher
    ActionExecutable = $pythonw
    ActionArguments = $actionArguments
    LaunchMode = "pythonw-create-no-window"
    Principal = $principalName
  } | ConvertTo-Json
  return
}

$task = Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Incrementally projects sanitized Codex task messages and revision-swaps them into NotebookLM." -Force

[pscustomobject]@{
  TaskName = $task.TaskName
  State = $task.State.ToString()
  IntervalMinutes = $Minutes
  ExecutionTimeLimitMinutes = $effectiveExecutionLimit
  Config = $configPath
  Runner = $runner
  Launcher = $launcher
  ActionExecutable = $pythonw
  LaunchMode = "pythonw-create-no-window"
  Principal = $principalName
} | ConvertTo-Json
