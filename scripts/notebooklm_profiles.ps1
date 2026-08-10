param(
  [Parameter(Mandatory = $true, Position = 0)]
  [ValidateSet("list", "check", "login-work", "login-personal", "master-login-work", "master-login-personal", "refresh-work", "refresh-personal", "refresh-all", "verify-work", "verify-personal", "lock-work", "lock-personal", "lock-all", "switch-work", "switch-personal", "doctor-work", "doctor-personal")]
  [string] $Action,
  [string] $Account,
  [ValidateSet("chromium", "chrome", "msedge")] [string] $Browser = "chromium",
  [string] $NotebookLmCli
)

$ErrorActionPreference = "Stop"

if (-not $NotebookLmCli) {
  $codexRoot = $env:CODEX_HOME
  if (-not $codexRoot) { $codexRoot = Join-Path $env:USERPROFILE ".codex" }
  $isolated = Join-Path $codexRoot "runtimes\notebooklm-py-0.8.0\Scripts\notebooklm.exe"
  if (Test-Path -LiteralPath $isolated) {
    $NotebookLmCli = $isolated
  } else {
    $command = Get-Command notebooklm -ErrorAction SilentlyContinue
    if (-not $command) { throw "notebooklm CLI not found. Install notebooklm-py in an isolated runtime or pass -NotebookLmCli." }
    $NotebookLmCli = $command.Source
  }
}

function Invoke-NotebookLm {
  param([string[]] $CliArgs)
  & $NotebookLmCli @CliArgs
  if ($LASTEXITCODE -ne 0) { throw "notebooklm exited with code $LASTEXITCODE" }
}

function Require-Account {
  if (-not $Account) { throw "-Account EMAIL is required for account-verified login or verification." }
}

function Assert-ProfileAccount {
  param([string] $Profile)
  Require-Account
  $raw = @(& $NotebookLmCli profile list --json 2>&1)
  if ($LASTEXITCODE -ne 0) { throw "Unable to inspect NotebookLM profiles (exit $LASTEXITCODE)." }
  $payload = ($raw -join "`n") | ConvertFrom-Json
  $match = @($payload.profiles | Where-Object { $_.name -eq $Profile })
  if ($match.Count -ne 1) { throw "Expected one NotebookLM profile named '$Profile'; found $($match.Count)." }
  if (-not $match[0].authenticated) { throw "NotebookLM profile '$Profile' is not authenticated." }
  if ([string]$match[0].account -ine $Account) {
    throw "NotebookLM profile '$Profile' is bound to a different Google account. Rerun with --fresh and the intended identity."
  }
  [pscustomobject]@{ Profile = $Profile; Account = $match[0].account; Authenticated = $true }
}

function Protect-ProfileDirectory {
  param([string] $Profile)
  if ($env:OS -ne "Windows_NT") { throw "Profile ACL locking is currently supported on Windows only." }
  $directory = Join-Path $env:USERPROFILE ".notebooklm\profiles\$Profile"
  if (-not (Test-Path -LiteralPath $directory)) { throw "NotebookLM profile directory not found: $directory" }
  $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
  & icacls.exe $directory /inheritance:r /grant:r "${identity}:(OI)(CI)F" "SYSTEM:(OI)(CI)F" | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Failed to restrict the '$Profile' directory ACL (exit $LASTEXITCODE)." }
  Get-ChildItem -Force -Recurse -LiteralPath $directory | ForEach-Object {
    if ($_.PSIsContainer) {
      & icacls.exe $_.FullName /inheritance:r /grant:r "${identity}:(OI)(CI)F" "SYSTEM:(OI)(CI)F" | Out-Null
    } else {
      & icacls.exe $_.FullName /inheritance:r /grant:r "${identity}:F" "SYSTEM:F" | Out-Null
    }
    if ($LASTEXITCODE -ne 0) { throw "Failed to restrict a '$Profile' profile item ACL (exit $LASTEXITCODE)." }
  }
  [pscustomobject]@{ Profile = $Profile; Directory = $directory; Locked = $true }
}

switch ($Action) {
  "list" {
    Invoke-NotebookLm -CliArgs @("profile", "list")
  }
  "check" {
    Invoke-NotebookLm -CliArgs @("-p", "work", "auth", "check", "--test", "--passive")
    Invoke-NotebookLm -CliArgs @("-p", "personal", "auth", "check", "--test", "--passive")
  }
  "login-work" {
    Require-Account
    Invoke-NotebookLm -CliArgs @("-p", "work", "login", "--browser", $Browser, "--fresh")
    Assert-ProfileAccount -Profile "work"
  }
  "login-personal" {
    Require-Account
    Invoke-NotebookLm -CliArgs @("-p", "personal", "login", "--browser", $Browser, "--fresh")
    Assert-ProfileAccount -Profile "personal"
  }
  "master-login-work" {
    Require-Account
    Invoke-NotebookLm -CliArgs @("-p", "work", "login", "--browser", $Browser, "--fresh", "--master-token", "--account", $Account)
    Assert-ProfileAccount -Profile "work"
    Protect-ProfileDirectory -Profile "work"
  }
  "master-login-personal" {
    Require-Account
    Invoke-NotebookLm -CliArgs @("-p", "personal", "login", "--browser", $Browser, "--fresh", "--master-token", "--account", $Account)
    Assert-ProfileAccount -Profile "personal"
    Protect-ProfileDirectory -Profile "personal"
  }
  "refresh-work" {
    Invoke-NotebookLm -CliArgs @("-p", "work", "auth", "refresh", "--verify")
  }
  "refresh-personal" {
    Invoke-NotebookLm -CliArgs @("-p", "personal", "auth", "refresh", "--verify")
  }
  "refresh-all" {
    Invoke-NotebookLm -CliArgs @("-p", "work", "auth", "refresh", "--verify")
    Invoke-NotebookLm -CliArgs @("-p", "personal", "auth", "refresh", "--verify")
  }
  "verify-work" {
    Assert-ProfileAccount -Profile "work"
  }
  "verify-personal" {
    Assert-ProfileAccount -Profile "personal"
  }
  "lock-work" {
    Protect-ProfileDirectory -Profile "work"
  }
  "lock-personal" {
    Protect-ProfileDirectory -Profile "personal"
  }
  "lock-all" {
    Protect-ProfileDirectory -Profile "work"
    Protect-ProfileDirectory -Profile "personal"
  }
  "switch-work" {
    Invoke-NotebookLm -CliArgs @("profile", "switch", "work")
  }
  "switch-personal" {
    Invoke-NotebookLm -CliArgs @("profile", "switch", "personal")
  }
  "doctor-work" {
    Invoke-NotebookLm -CliArgs @("-p", "work", "doctor")
  }
  "doctor-personal" {
    Invoke-NotebookLm -CliArgs @("-p", "personal", "doctor")
  }
}
