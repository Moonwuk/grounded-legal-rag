[CmdletBinding()]
param([string]$Root = (Join-Path $env:LOCALAPPDATA 'PsbLegalWeb'))
. (Join-Path $PSScriptRoot 'common.ps1')
Invoke-Locked {
    $release = Get-ActiveRelease
    Invoke-ReleaseCompose $release 'psb-managed' $release.port @('restart')
    Start-Release $release
    Write-DeployLog 'Managed site restarted and healthy.'
}
