function Test-ScheduledTaskHealth {
  [CmdletBinding()]
  param(
    [Parameter(Mandatory = $true)] [string] $State,
    [Parameter(Mandatory = $true)] [int] $LastTaskResult
  )

  $activeState = $State -in @("Running", "Queued")
  [pscustomobject]@{
    Passed = $State -ne "Disabled" -and ($LastTaskResult -eq 0 -or $activeState)
    Active = $activeState
  }
}
