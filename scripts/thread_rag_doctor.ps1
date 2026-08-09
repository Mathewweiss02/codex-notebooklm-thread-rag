param(
  [Parameter(Mandatory = $true)] [string] $Config,
  [switch] $Live,
  [switch] $RefreshAuth,
  [string] $TaskName
)

$ErrorActionPreference = "Stop"
$configPath = (Resolve-Path -LiteralPath $Config).Path
$settings = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$checks = @()
$failed = $false

function Add-Check {
  param([string] $Name, [bool] $Passed, [string] $Detail)
  $script:checks += [pscustomobject]@{ Name = $Name; Passed = $Passed; Detail = $Detail }
  if (-not $Passed) { $script:failed = $true }
}

foreach ($name in @("Device", "ProjectionRoot", "Profile", "NotebookId", "NodePath", "PythonPath", "NotebookLmCli", "ProjectionScript", "SyncScript")) {
  Add-Check "config-$name" ([bool]$settings.$name) $(if ($settings.$name) { "present" } else { "missing" })
}
foreach ($name in @("NodePath", "PythonPath", "NotebookLmCli", "ProjectionScript", "SyncScript")) {
  $value = [string]$settings.$name
  Add-Check "path-$name" (Test-Path -LiteralPath $value) $value
}
$threadIds = @($settings.ThreadIds | Where-Object { $_ })
Add-Check "scope-gate" ($threadIds.Count -gt 0 -or $settings.AllowAllThreads -eq $true) ("threads={0}; allowAll={1}" -f $threadIds.Count, [bool]$settings.AllowAllThreads)

$statePath = Join-Path ([string]$settings.ProjectionRoot) "state.json"
Add-Check "projection-state" (Test-Path -LiteralPath $statePath) $statePath
if (Test-Path -LiteralPath $statePath) {
  $state = Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json
  Add-Check "projection-policy" ([string]$state.policyVersion -eq "visible-messages-secrets-redacted-v6") ([string]$state.policyVersion)
  Add-Check "projection-threads" (@($state.threads.PSObject.Properties).Count -gt 0) ("count={0}" -f @($state.threads.PSObject.Properties).Count)
}

$runnerStatePath = Join-Path ([string]$settings.ProjectionRoot) "runner_state.json"
Add-Check "runner-state" (Test-Path -LiteralPath $runnerStatePath) $runnerStatePath
if (Test-Path -LiteralPath $runnerStatePath) {
  $runnerState = Get-Content -Raw -LiteralPath $runnerStatePath | ConvertFrom-Json
  Add-Check "runner-last-success" ([bool]$runnerState.LastSuccessAt) ([string]$runnerState.LastSuccessAt)
}

if (-not $TaskName) {
  try {
    $matchingTasks = @(Get-ScheduledTask -ErrorAction Stop | Where-Object {
      @($_.Actions | Where-Object { [string]$_.Arguments -like "*$configPath*" }).Count -gt 0
    })
    if ($matchingTasks.Count -eq 1) { $TaskName = [string]$matchingTasks[0].TaskName }
  } catch {
    # Scheduler inspection is optional until a task has been installed.
  }
}
if ($TaskName) {
  try {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    $taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
    $schedulerHealthy = $taskInfo.LastTaskResult -eq 0 -and [string]$task.State -ne "Disabled"
    Add-Check "scheduled-task" $schedulerHealthy ("name={0}; state={1}; lastResult={2}; next={3}" -f $TaskName, $task.State, $taskInfo.LastTaskResult, $taskInfo.NextRunTime)
  } catch {
    Add-Check "scheduled-task" $false $_.Exception.Message
  }
}

if ($RefreshAuth) {
  & ([string]$settings.NotebookLmCli) -p ([string]$settings.Profile) login --master-token-refresh | Out-Null
  Add-Check "master-token-refresh" ($LASTEXITCODE -eq 0) ("exit={0}" -f $LASTEXITCODE)
}
if ($Live) {
  & ([string]$settings.NotebookLmCli) -p ([string]$settings.Profile) auth check --test --passive --json | Out-Null
  Add-Check "live-auth-passive" ($LASTEXITCODE -eq 0) ("exit={0}" -f $LASTEXITCODE)
  & ([string]$settings.PythonPath) ([string]$settings.SyncScript) --state $statePath --profile ([string]$settings.Profile) --notebook-id ([string]$settings.NotebookId) --validate-only | Out-Null
  Add-Check "live-source-reconcile" ($LASTEXITCODE -eq 0) ("exit={0}" -f $LASTEXITCODE)
}

$result = [ordered]@{ Status = $(if ($failed) { "error" } else { "ok" }); Config = $configPath; Live = [bool]$Live; Checks = $checks }
$result | ConvertTo-Json -Depth 8
if ($failed) { exit 1 }
