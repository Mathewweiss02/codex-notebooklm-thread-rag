param(
  [Parameter(Mandatory = $true)] [string] $Doctor
)

$ErrorActionPreference = "Stop"
function Assert-True { param([bool] $Condition, [string] $Message) if (-not $Condition) { throw "Assertion failed: $Message" } }

$doctorLib = Join-Path (Split-Path -Parent $Doctor) "thread_rag_doctor_lib.ps1"
. $doctorLib
$ready = Test-ScheduledTaskHealth -State "Ready" -LastTaskResult 0
$running = Test-ScheduledTaskHealth -State "Running" -LastTaskResult 267009
$disabled = Test-ScheduledTaskHealth -State "Disabled" -LastTaskResult 0
$failed = Test-ScheduledTaskHealth -State "Ready" -LastTaskResult 1
Assert-True $ready.Passed "successful ready task must pass"
Assert-True $running.Passed -and $running.Active "currently running task result must not be a false failure"
Assert-True (-not $disabled.Passed) "disabled task must fail"
Assert-True (-not $failed.Passed) "failed ready task must fail"

$temporary = Join-Path ([System.IO.Path]::GetTempPath()) ("thread-rag-doctor-test-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $temporary -Force | Out-Null
try {
  $ok = Join-Path $temporary "ok.cmd"
  $authError = Join-Path $temporary "auth-error.cmd"
  Set-Content -LiteralPath $ok -Encoding Ascii -Value @("@echo {}", "@exit /b 0")
  Set-Content -LiteralPath $authError -Encoding Ascii -Value @('@echo {"status":"error","profile":"fixture"}', "@exit /b 0")
  $root = Join-Path $temporary "state"
  New-Item -ItemType Directory -Path $root -Force | Out-Null
  $projection = Join-Path $temporary "projection.mjs"
  $sync = Join-Path $temporary "sync.py"
  Set-Content -LiteralPath $projection -Value "// fixture"
  Set-Content -LiteralPath $sync -Value "# fixture"
  @{ policyVersion = "visible-messages-secrets-redacted-v4"; threads = @{ fixture = @{} } } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $root "state.json") -Encoding UTF8
  $configPath = Join-Path $temporary "config.json"
  $config = [ordered]@{
    Device = "fixture"; ProjectionRoot = $root; Profile = "fixture"; NotebookId = "notebook"
    NodePath = $ok; PythonPath = $ok; NotebookLmCli = $authError; ProjectionScript = $projection; SyncScript = $sync
    ThreadIds = @("fixture"); AllowAllThreads = $false; MaxRunnerAgeMinutes = 45; RejectUntrackedSources = $true
    NotebookRole = "retrieval"; DisposableSearchChat = $true; ConversationPolicy = "dedicated-retrieval-disposable-v1"
  }
  $config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $configPath -Encoding UTF8

  @{ LastSuccessAt = (Get-Date).ToUniversalTime().AddHours(-2).ToString("o"); LastStatus = "ok" } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root "runner_state.json") -Encoding UTF8
  $staleRaw = @(& $Doctor -Config $configPath 2>$null)
  $stale = ($staleRaw -join "`n") | ConvertFrom-Json
  Assert-True ($stale.Status -eq "error") "stale historical success must fail"
  Assert-True (-not @($stale.Checks | Where-Object Name -eq "runner-last-success")[0].Passed) "runner age check must fail"

  @{ LastSuccessAt = (Get-Date).ToUniversalTime().ToString("o"); LastStatus = "ok" } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root "runner_state.json") -Encoding UTF8
  $liveRaw = @(& $Doctor -Config $configPath -Live 2>$null)
  $live = ($liveRaw -join "`n") | ConvertFrom-Json
  $authCheck = @($live.Checks | Where-Object Name -eq "live-auth-passive")[0]
  Assert-True ($live.Status -eq "error") "JSON auth error must fail even when exit code is zero"
  Assert-True (-not $authCheck.Passed) "auth status must be parsed"
  Assert-True ($authCheck.Detail -match "status=error") "auth detail must retain parsed status"

  $global:LASTEXITCODE = 0
  [pscustomobject]@{ Status = "passed"; Checks = 5 } | ConvertTo-Json
} finally {
  if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
