param(
  [Parameter(Mandatory = $true, Position = 0)]
  [ValidateSet("list", "check", "login-work", "login-personal", "master-login-work", "master-login-personal", "refresh-work", "refresh-personal", "refresh-all", "switch-work", "switch-personal", "doctor-work", "doctor-personal")]
  [string] $Action,
  [string] $Account,
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
  if (-not $Account) { throw "-Account EMAIL is required for master-token login." }
}

switch ($Action) {
  "list" {
    Invoke-NotebookLm -CliArgs @("profile", "list")
  }
  "check" {
    Invoke-NotebookLm -CliArgs @("-p", "work", "auth", "check")
    Invoke-NotebookLm -CliArgs @("-p", "personal", "auth", "check")
  }
  "login-work" {
    Invoke-NotebookLm -CliArgs @("-p", "work", "login", "--browser", "chrome")
  }
  "login-personal" {
    Invoke-NotebookLm -CliArgs @("-p", "personal", "login", "--browser", "chrome", "--fresh")
  }
  "master-login-work" {
    Require-Account
    Invoke-NotebookLm -CliArgs @("-p", "work", "login", "--browser", "chrome", "--fresh", "--master-token", "--account", $Account)
  }
  "master-login-personal" {
    Require-Account
    Invoke-NotebookLm -CliArgs @("-p", "personal", "login", "--browser", "chrome", "--fresh", "--master-token", "--account", $Account)
  }
  "refresh-work" {
    Invoke-NotebookLm -CliArgs @("-p", "work", "login", "--master-token-refresh")
  }
  "refresh-personal" {
    Invoke-NotebookLm -CliArgs @("-p", "personal", "login", "--master-token-refresh")
  }
  "refresh-all" {
    Invoke-NotebookLm -CliArgs @("-p", "work", "login", "--master-token-refresh")
    Invoke-NotebookLm -CliArgs @("-p", "personal", "login", "--master-token-refresh")
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
