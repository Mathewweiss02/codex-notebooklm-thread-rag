param(
  [Parameter(Mandatory = $true)]
  [string] $Config,
  [string] $TaskName = "Codex NotebookLM Thread Sync",
  [ValidateRange(10, 1440)]
  [int] $Minutes = 15,
  [ValidateRange(15, 1440)]
  [int] $ExecutionLimitMinutes = 120,
  [switch] $Remove
)

$ErrorActionPreference = "Stop"
$configPath = (Resolve-Path -LiteralPath $Config).Path
$runner = Join-Path $PSScriptRoot "notebooklm_thread_sync_runner.ps1"
if (-not (Test-Path -LiteralPath $runner)) { throw "Runner not found: $runner" }

if ($Remove) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
  [pscustomobject]@{ TaskName = $TaskName; Status = "removed" } | ConvertTo-Json
  return
}

$principalName = "$env:USERDOMAIN\$env:USERNAME"
$quotedRunner = '"' + $runner + '"'
$quotedConfig = '"' + $configPath + '"'
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File $quotedRunner -Config $quotedConfig"
$recurringTrigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes $Minutes)
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $principalName
$principal = New-ScheduledTaskPrincipal -UserId $principalName -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes $ExecutionLimitMinutes) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$task = Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($recurringTrigger, $logonTrigger) -Principal $principal -Settings $settings -Description "Incrementally projects sanitized Codex task messages and revision-swaps them into NotebookLM." -Force

[pscustomobject]@{
  TaskName = $task.TaskName
  State = $task.State.ToString()
  IntervalMinutes = $Minutes
  ExecutionLimitMinutes = $ExecutionLimitMinutes
  Config = $configPath
  Runner = $runner
  Principal = $principalName
} | ConvertTo-Json
