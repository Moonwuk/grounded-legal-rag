[CmdletBinding()]
param([string]$Root = (Join-Path $env:LOCALAPPDATA 'PsbLegalWeb'))
. (Join-Path $PSScriptRoot 'common.ps1')
$release = Read-State $StatePath
if (-not $release) { throw 'No managed release is active.' }
Test-HttpHealth $release.port
