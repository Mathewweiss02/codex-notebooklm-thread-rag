param(
  [Parameter(Mandatory = $true)] [string] $Config,
  [switch] $Live,
  [switch] $RefreshAuth,
  [string] $TaskName,
  [ValidateRange(1, 10080)] [int] $MaxRunnerAgeMinutes = 45
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "notebooklm_auth_helpers.ps1")
$configPath = (Resolve-Path -LiteralPath $Config).Path
$settings = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$checks = @()
$failed = $false

function Add-Check {
  param([string] $Name, [bool] $Passed, [string] $Detail)
  $script:checks += [pscustomobject]@{ Name = $Name; Passed = $Passed; Detail = $Detail }
  if (-not $Passed) { $script:failed = $true }
}

foreach ($name in @("Device", "ProjectionRoot", "Profile", "NotebookId", "NotebookRole", "NodePath", "PythonPath", "NotebookLmCli", "ProjectionScript", "SyncScript")) {
  Add-Check "config-$name" ([bool]$settings.$name) $(if ($settings.$name) { "present" } else { "missing" })
}
foreach ($name in @("NodePath", "PythonPath", "NotebookLmCli", "ProjectionScript", "SyncScript")) {
  $value = [string]$settings.$name
  Add-Check "path-$name" (Test-Path -LiteralPath $value) $value
}
$threadIds = @($settings.ThreadIds | Where-Object { $_ })
Add-Check "scope-gate" ($threadIds.Count -gt 0 -or $settings.AllowAllThreads -eq $true) ("threads={0}; allowAll={1}" -f $threadIds.Count, [bool]$settings.AllowAllThreads)
$conversationSafe = if ([string]$settings.NotebookRole -eq "retrieval") { $settings.DisposableSearchChat -eq $true } else { [string]$settings.NotebookRole -eq "chat" -and $settings.DisposableSearchChat -ne $true }
Add-Check "conversation-policy" $conversationSafe ("role={0}; disposable={1}; policy={2}" -f [string]$settings.NotebookRole, [bool]$settings.DisposableSearchChat, [string]$settings.ConversationPolicy)

$statePath = Join-Path ([string]$settings.ProjectionRoot) "state.json"
Add-Check "projection-state" (Test-Path -LiteralPath $statePath) $statePath
if (Test-Path -LiteralPath $statePath) {
  $state = Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json
  Add-Check "projection-policy" ([string]$state.policyVersion -eq "visible-messages-secrets-redacted-v4") ([string]$state.policyVersion)
  Add-Check "projection-threads" (@($state.threads.PSObject.Properties).Count -gt 0) ("count={0}" -f @($state.threads.PSObject.Properties).Count)
}

$runnerStatePath = Join-Path ([string]$settings.ProjectionRoot) "runner_state.json"
Add-Check "runner-state" (Test-Path -LiteralPath $runnerStatePath) $runnerStatePath
if (Test-Path -LiteralPath $runnerStatePath) {
  $runnerState = Get-Content -Raw -LiteralPath $runnerStatePath | ConvertFrom-Json
  $configuredMaxAge = if ($null -ne $settings.MaxRunnerAgeMinutes) { [int]$settings.MaxRunnerAgeMinutes } else { $MaxRunnerAgeMinutes }
  try {
    $lastSuccess = [DateTimeOffset]::Parse([string]$runnerState.LastSuccessAt).ToUniversalTime()
    $ageMinutes = ([DateTimeOffset]::UtcNow - $lastSuccess).TotalMinutes
    $runnerFresh = $ageMinutes -ge -5 -and $ageMinutes -le $configuredMaxAge
    Add-Check "runner-last-success" $runnerFresh ("at={0}; ageMinutes={1:N1}; maxMinutes={2}" -f $lastSuccess.ToString("o"), $ageMinutes, $configuredMaxAge)
  } catch {
    Add-Check "runner-last-success" $false ("invalid timestamp: {0}" -f [string]$runnerState.LastSuccessAt)
  }
  if ($runnerState.LastStatus) {
    Add-Check "runner-last-status" ([string]$runnerState.LastStatus -eq "ok") ("status={0}; attempt={1}" -f [string]$runnerState.LastStatus, [string]$runnerState.LastAttemptAt)
  }
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
    $matchingAction = @($task.Actions | Where-Object { [string]$_.Arguments -like "*$configPath*" } | Select-Object -First 1)
    $actionExecutable = if ($matchingAction.Count) { [string]$matchingAction[0].Execute } else { "" }
    $actionArguments = if ($matchingAction.Count) { [string]$matchingAction[0].Arguments } else { "" }
    $consoleFree = $matchingAction.Count -eq 1 -and (Split-Path -Leaf $actionExecutable) -like "pythonw*.exe" -and $actionArguments -like "*notebooklm_thread_sync_hidden.pyw*"
    Add-Check "scheduled-task-console-free" $consoleFree ("execute={0}; launcher={1}" -f $actionExecutable, $(if ($actionArguments -like "*notebooklm_thread_sync_hidden.pyw*") { "present" } else { "missing" }))
  } catch {
    Add-Check "scheduled-task" $false $_.Exception.Message
  }
}

if ($RefreshAuth) {
  & ([string]$settings.NotebookLmCli) -p ([string]$settings.Profile) auth refresh --verify | Out-Null
  Add-Check "auth-refresh" ($LASTEXITCODE -eq 0) ("exit={0}" -f $LASTEXITCODE)
}
if ($Live) {
  $auth = Invoke-NotebookLmAuthJson -NotebookLmCli ([string]$settings.NotebookLmCli) -Profile ([string]$settings.Profile)
  Add-Check "live-auth-passive" $auth.Passed $auth.Detail
  $validateArgs = @(([string]$settings.SyncScript), "--state", $statePath, "--profile", ([string]$settings.Profile), "--notebook-id", ([string]$settings.NotebookId), "--validate-only")
  if ($settings.RejectUntrackedSources -eq $true) { $validateArgs += "--reject-untracked-sources" }
  & ([string]$settings.PythonPath) @validateArgs | Out-Null
  Add-Check "live-source-reconcile" ($LASTEXITCODE -eq 0) ("exit={0}" -f $LASTEXITCODE)
}

$result = [ordered]@{ Status = $(if ($failed) { "error" } else { "ok" }); Config = $configPath; Live = [bool]$Live; Checks = $checks }
$result | ConvertTo-Json -Depth 8
if ($failed) { exit 1 }
