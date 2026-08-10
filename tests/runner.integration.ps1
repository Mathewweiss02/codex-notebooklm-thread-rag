param(
  [Parameter(Mandatory = $true)] [string] $Runner
)

$ErrorActionPreference = "Stop"

function Assert-True {
  param([bool] $Condition, [string] $Message)
  if (-not $Condition) { throw "Assertion failed: $Message" }
}

$temporary = Join-Path ([System.IO.Path]::GetTempPath()) ("thread-rag-runner-test-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $temporary -Force | Out-Null
try {
  $ok = Join-Path $temporary "ok.cmd"
  $fail = Join-Path $temporary "fail.cmd"
  $signal = Join-Path $temporary "slow-started.txt"
  $slow = Join-Path $temporary "slow.cmd"
  Set-Content -LiteralPath $ok -Encoding Ascii -Value @("@echo harmless native warning 1>&2", "@echo %*", "@exit /b 0")
  Set-Content -LiteralPath $fail -Encoding Ascii -Value @("@echo simulated failure 1>&2", "@exit /b 7")
  Set-Content -LiteralPath $slow -Encoding Ascii -Value @("@echo started>$signal", "@ping -n 3 127.0.0.1 >nul", "@exit /b 0")

  $root = Join-Path $temporary "state"
  $configPath = Join-Path $temporary "config.json"
  $config = [ordered]@{
    Device = "runner-fixture"
    ProjectionRoot = $root
    Profile = "fixture"
    NotebookId = "fixture-notebook"
    NodePath = $ok
    PythonPath = $ok
    NotebookLmCli = $ok
    ProjectionScript = "projection-placeholder"
    SyncScript = "sync-placeholder"
    QuietMinutes = 60
    HardMaxHours = 6
    MaxWords = 120000
    MaxMessageChars = 100000
    MaxLineBytes = 8388608
    WaitTimeout = 5
    RefreshAuth = $true
    SwapOld = $true
    ReconcileHour = 0
    AllowAllThreads = $false
    ThreadIds = @("fixture-thread")
  }
  $config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $configPath -Encoding UTF8

  $result = (& $Runner -Config $configPath) | ConvertFrom-Json
  Assert-True ($result.Status -eq "ok") "benign native stderr must not fail a zero-exit command"
  $run = Get-Content -Raw -LiteralPath $result.Run | ConvertFrom-Json
  Assert-True ($run.Steps.Count -ge 3) "normal run must execute auth, projection, and sync"
  Assert-True ((Test-Path -LiteralPath (Join-Path $root "runner_state.json"))) "runner checkpoint must be written"

  $dryResult = (& $Runner -Config $configPath -DryRun) | ConvertFrom-Json
  $dryRun = Get-Content -Raw -LiteralPath $dryResult.Run | ConvertFrom-Json
  $dryProjection = @($dryRun.Steps | Where-Object Label -eq "projection")[0]
  $drySync = @($dryRun.Steps | Where-Object Label -eq "sync")[0]
  Assert-True ((@($dryProjection.OutputTail) -join " ") -notmatch "--dry-run") "runner dry-run must materialize local projection state"
  Assert-True ((@($drySync.OutputTail) -join " ") -match "--dry-run") "runner dry-run must keep remote sync write-free"

  $reconcile = (& $Runner -Config $configPath -ReconcileOnly) | ConvertFrom-Json
  $reconcileRun = Get-Content -Raw -LiteralPath $reconcile.Run | ConvertFrom-Json
  Assert-True (@($reconcileRun.Steps.Label) -contains "nightly-reconcile") "reconcile-only must validate live lineage"

  $unsafePath = Join-Path $temporary "unsafe.json"
  $config.ThreadIds = @()
  $config.AllowAllThreads = $false
  $config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $unsafePath -Encoding UTF8
  $scopeFailed = $false
  try { & $Runner -Config $unsafePath | Out-Null } catch { $scopeFailed = $_.Exception.Message -match "AllowAllThreads" }
  Assert-True $scopeFailed "empty scope must fail unless AllowAllThreads is explicit"

  $errorRoot = Join-Path $temporary "error-state"
  $errorPath = Join-Path $temporary "error.json"
  $config.ThreadIds = @("fixture-thread")
  $config.ProjectionRoot = $errorRoot
  $config.PythonPath = $fail
  $config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $errorPath -Encoding UTF8
  try { & $Runner -Config $errorPath | Out-Null } catch { }
  $errorLog = Get-ChildItem -LiteralPath (Join-Path $errorRoot "runs") -Filter "runner-*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  $errorRun = Get-Content -Raw -LiteralPath $errorLog.FullName | ConvertFrom-Json
  Assert-True ($errorRun.Status -eq "error") "nonzero child exit must be durably logged"

  $slowRoot = Join-Path $temporary "slow-state"
  $slowPath = Join-Path $temporary "slow.json"
  $config.ProjectionRoot = $slowRoot
  $config.NodePath = $slow
  $config.PythonPath = $slow
  $config.NotebookLmCli = $slow
  $config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $slowPath -Encoding UTF8
  $runnerQuoted = '"' + $Runner + '"'
  $configQuoted = '"' + $slowPath + '"'
  $process = Start-Process powershell.exe -WindowStyle Hidden -PassThru -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File $runnerQuoted -Config $configQuoted"
  # GitHub may run the push and pull-request workflows concurrently on the
  # same Windows host pool, so process startup can exceed the local 8s budget.
  $deadline = (Get-Date).AddSeconds(30)
  while (-not (Test-Path -LiteralPath $signal) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 100 }
  Assert-True (Test-Path -LiteralPath $signal) "slow runner must acquire mutex and signal"
  $overlap = (& $Runner -Config $slowPath) | ConvertFrom-Json
  Assert-True ($overlap.Status -eq "skipped-overlap") "second runner must skip while mutex is held"
  $process.WaitForExit(60000) | Out-Null
  Assert-True ($process.ExitCode -eq 0) "first slow runner must finish successfully"

  $global:LASTEXITCODE = 0
  [pscustomobject]@{ Status = "passed"; Checks = 10; TempRoot = $temporary } | ConvertTo-Json
} finally {
  if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
