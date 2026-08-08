param(
  [Parameter(Mandatory = $true)] [string] $ProfileScript
)

$ErrorActionPreference = "Stop"
function Assert-True { param([bool] $Condition, [string] $Message) if (-not $Condition) { throw "Assertion failed: $Message" } }

$temporary = Join-Path ([System.IO.Path]::GetTempPath()) ("thread-rag-acl-test-" + [guid]::NewGuid().ToString("N"))
$priorUserProfile = $env:USERPROFILE
try {
  $env:USERPROFILE = $temporary
  $profileDir = Join-Path $temporary ".notebooklm\profiles\work"
  New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
  $first = Join-Path $profileDir "master_token.json"
  $second = Join-Path $profileDir "storage_state.json"
  Set-Content -LiteralPath $first -Value "{}" -Encoding UTF8
  Set-Content -LiteralPath $second -Value "{}" -Encoding UTF8
  & $ProfileScript lock-work -NotebookLmCli "$env:WINDIR\System32\where.exe" | Out-Null
  $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
  foreach ($file in @($first, $second)) {
    $acl = Get-Acl -LiteralPath $file
    $userAce = @($acl.Access | Where-Object { $_.IdentityReference -eq $identity -and $_.FileSystemRights.ToString() -match "FullControl" })
    $systemAce = @($acl.Access | Where-Object { $_.IdentityReference -eq "NT AUTHORITY\SYSTEM" -and $_.FileSystemRights.ToString() -match "FullControl" })
    Assert-True ($userAce.Count -eq 1) "profile file must grant the current user full control"
    Assert-True ($systemAce.Count -eq 1) "profile file must grant SYSTEM full control"
    Assert-True (@($acl.Access).Count -eq 2) "profile file must not retain broader ACL entries"
  }
  [pscustomobject]@{ Status = "passed"; Checks = 6 } | ConvertTo-Json
} finally {
  $env:USERPROFILE = $priorUserProfile
  if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
