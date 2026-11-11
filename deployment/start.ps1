[CmdletBinding()]
param([string]$Root = (Join-Path $env:LOCALAPPDATA 'PsbLegalWeb'))
. (Join-Path $PSScriptRoot 'common.ps1')
Invoke-Locked {
    $release = Get-ActiveRelease
    Start-Release $release
    Write-DeployLog "Started http://127.0.0.1:$($release.port)/."
}
