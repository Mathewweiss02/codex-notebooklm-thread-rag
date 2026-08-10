param(
  [Parameter(Mandatory = $true)] [string] $ProfileScript
)

$ErrorActionPreference = "Stop"
function Assert-True { param([bool] $Condition, [string] $Message) if (-not $Condition) { throw "Assertion failed: $Message" } }

$temporary = Join-Path ([System.IO.Path]::GetTempPath()) ("thread-rag-auth-test-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $temporary -Force | Out-Null
try {
  $authError = Join-Path $temporary "auth-error.cmd"
  Set-Content -LiteralPath $authError -Encoding Ascii -Value @('@echo {"status":"error","profile":"fixture"}', "@exit /b 0")
  $failed = $false
  try { & $ProfileScript check -NotebookLmCli $authError | Out-Null } catch { $failed = $_.Exception.Message -match "status=error" }
  Assert-True $failed "profile check must reject status=error with exit code zero"
  $global:LASTEXITCODE = 0
  [pscustomobject]@{ Status = "passed"; Checks = 1 } | ConvertTo-Json
} finally {
  if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
