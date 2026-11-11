[CmdletBinding()]
param([string]$Root = (Join-Path $env:LOCALAPPDATA 'PsbLegalWeb'))
. (Join-Path $PSScriptRoot 'common.ps1')
Invoke-Locked {
    $release = Get-ActiveRelease
    Write-DeployLog "Release $($release.sha) on port $($release.port)."
    $waiting = Read-State $WaitingPath
    if ($waiting -and $waiting.sha -ne $release.sha) { Write-Warning "Newer main $($waiting.sha) is not deployed: $($waiting.reason)" }
    Invoke-ReleaseCompose $release 'psb-managed' $release.port @('ps','-a')
    Test-HttpHealth $release.port
}
