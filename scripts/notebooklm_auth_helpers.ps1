function Invoke-NotebookLmAuthJson {
  param(
    [Parameter(Mandatory = $true)] [string] $NotebookLmCli,
    [Parameter(Mandatory = $true)] [string] $Profile
  )

  $priorPreference = $ErrorActionPreference
  $hasNativePreference = Test-Path variable:PSNativeCommandUseErrorActionPreference
  if ($hasNativePreference) { $priorNativePreference = $PSNativeCommandUseErrorActionPreference }
  try {
    $ErrorActionPreference = "Continue"
    if ($hasNativePreference) { $PSNativeCommandUseErrorActionPreference = $false }
    $raw = @(& $NotebookLmCli -p $Profile auth check --test --passive --json)
    $exitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $priorPreference
    if ($hasNativePreference) { $PSNativeCommandUseErrorActionPreference = $priorNativePreference }
  }

  $payload = $null
  $parseError = $null
  try {
    $payload = ($raw -join "`n") | ConvertFrom-Json
  } catch {
    $parseError = $_.Exception.Message
  }
  $status = if ($payload -and $payload.status) { [string]$payload.status } elseif ($parseError) { "invalid-json" } else { "missing-status" }
  $passed = $exitCode -eq 0 -and $status -eq "ok"
  $detail = "profile={0}; exit={1}; status={2}" -f $Profile, $exitCode, $status
  if ($parseError) { $detail += "; parseError=$parseError" }
  [pscustomobject]@{
    Passed = $passed
    ExitCode = $exitCode
    Status = $status
    Detail = $detail
    Payload = $payload
  }
}

function Assert-NotebookLmAuthJson {
  param(
    [Parameter(Mandatory = $true)] [string] $NotebookLmCli,
    [Parameter(Mandatory = $true)] [string] $Profile
  )
  $result = Invoke-NotebookLmAuthJson -NotebookLmCli $NotebookLmCli -Profile $Profile
  if (-not $result.Passed) { throw "NotebookLM auth check failed: $($result.Detail)" }
  $result
}
