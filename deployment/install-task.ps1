[CmdletBinding()]
param(
    [string]$Root = (Join-Path $env:LOCALAPPDATA 'PsbLegalWeb'),
    [ValidateRange(1024,65535)][int]$Port = 8001,
    [string]$CopyEnvFrom,
    [ValidateSet('Required','CiOnly')][string]$ApprovalPolicy = 'Required'
)
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($Root)
$pwsh = (Get-Command pwsh -ErrorAction Stop).Source
$stable = Join-Path $Root 'agent'
New-Item -ItemType Directory -Path $stable -Force | Out-Null
$names = 'common.ps1','start.ps1','stop.ps1','status.ps1','restart.ps1','healthcheck.ps1','update.ps1'
foreach ($name in $names) {
    $source = Join-Path $PSScriptRoot $name
    $destination = Join-Path $stable $name
    if ($source -ne $destination) { Copy-Item -LiteralPath $source -Destination $destination }
}
$envFile = Join-Path $Root '.env'
if ($CopyEnvFrom -and -not (Test-Path -LiteralPath $envFile)) {
    [IO.File]::Copy((Resolve-Path -LiteralPath $CopyEnvFrom).Path, $envFile, $false)
}
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw "Create $envFile, or supply -CopyEnvFrom for the initial installation."
}
$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$agent = Join-Path $stable 'update.ps1'
$action = New-ScheduledTaskAction -Execute $pwsh -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -File `"$agent`" -Root `"$Root`" -Port $Port -ApprovalPolicy $ApprovalPolicy -StartDocker"
$triggers = @(
    (New-ScheduledTaskTrigger -AtLogOn -User $user)
    (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 10))
)
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName 'PsbLegalWeb-Update' -Action $action -Trigger $triggers -Principal $principal -Settings $settings -Force
