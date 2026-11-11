Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($Root)
$StatePath = Join-Path $Root 'active.json'
$JournalPath = Join-Path $Root 'pending.json'
$RejectedPath = Join-Path $Root 'rejected.json'
$Repository = Join-Path $Root 'repository.git'
$EnvFile = Join-Path $Root '.env'
$EmptyEnv = Join-Path $Root 'stage.env'
$ReleaseRoot = Join-Path $Root 'releases'
$Log = Join-Path $Root 'deployment.log'
$GitHubRepository = 'Moonwuk/grounded-legal-rag'
$Remote = 'https://github.com/Moonwuk/grounded-legal-rag.git'

function Write-DeployLog([string]$Message) {
    Add-Content -LiteralPath $Log -Value ('{0:o} {1}' -f [DateTimeOffset]::Now, $Message)
    Write-Host $Message
}

function Assert-Engine([switch]$StartDesktop) {
    foreach ($tool in 'docker','git') {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Missing dependency: $tool" }
    }
    & docker compose version --short | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose is unavailable.' }
    & docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { return }
    if ($StartDesktop) {
        Write-DeployLog 'Docker engine is offline. Starting Docker Desktop.'
        & docker desktop start --timeout 120
        if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop could not be started.' }
        & docker info --format '{{.ServerVersion}}' | Out-Null
        if ($LASTEXITCODE -eq 0) { return }
    }
    throw 'Start Docker Desktop and wait for the engine.'
}

function Read-State([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    }
}

function Write-State([string]$Path, $Value) {
    $temp = "$Path.tmp"
    $Value | ConvertTo-Json -Depth 5 -Compress | Set-Content -LiteralPath $temp -Encoding utf8
    [IO.File]::Move($temp, $Path, $true)
}

function Invoke-ReleaseCompose($Release, [string]$Project, [string]$Port, [string[]]$Arguments, [switch]$Stage) {
    if ($Release.sha -notmatch '\A[0-9a-f]{40}\z') { throw 'Invalid release SHA.' }
    $folder = Join-Path $ReleaseRoot $Release.sha
    $compose = Join-Path $folder 'compose.yaml'
    $envPath = if ($Stage) { $EmptyEnv } else { $EnvFile }
    $overrides = @{
        WEB_BIND = '127.0.0.1'
        WEB_PORT = $Port
        WEB_IMAGE = "psb-managed:$($Release.sha)"
    }
    if ($Stage) {
        $overrides.LLM_BASE_URL = ''
        $overrides.LLM_API_KEY = ''
        $overrides.LLM_MODEL = ''
    }
    $saved = @{}
    foreach ($name in $overrides.Keys) {
        $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $overrides[$name], 'Process')
    }
    try {
        & docker compose --project-name $Project --project-directory $folder --env-file $envPath -f $compose @Arguments
        if ($LASTEXITCODE -ne 0) { throw "Compose $($Arguments[0]) failed for $Project (exit $LASTEXITCODE)." }
    } finally {
        foreach ($name in $saved.Keys) {
            [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process')
        }
    }
}

function Test-HttpHealth([int]$ListenPort) {
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:$ListenPort/healthz" -TimeoutSec 5
    if ($response.status -ne 'ok' -or $response.documents -lt 1 -or $response.fragments -lt 1) {
        throw "Unhealthy corpus on port $ListenPort."
    }
    $indexResponse = Invoke-WebRequest -Uri "http://127.0.0.1:$ListenPort/" -TimeoutSec 5
    if ($indexResponse.StatusCode -ne 200) { throw 'Web entry point is unhealthy.' }
    return $response
}

function Assert-ManagedPort([int]$ListenPort) {
    $listeners = Get-NetTCPConnection -State Listen -LocalPort $ListenPort -ErrorAction SilentlyContinue
    if (-not $listeners) { return }
    $ids = @(& docker ps --filter 'label=com.docker.compose.project=psb-managed' --filter 'label=com.docker.compose.service=web' --format '{{.ID}}')
    if ($LASTEXITCODE -ne 0) { throw 'Could not identify the managed container.' }
    if ($ids.Count -eq 1) {
        $mapping = & docker port $ids[0] '8000/tcp'
        if ($LASTEXITCODE -eq 0 -and $mapping -contains "127.0.0.1:$ListenPort") { return }
    }
    throw "Port $ListenPort is occupied by another service."
}

function Start-Release($Release) {
    Assert-ManagedPort $Release.port
    Invoke-ReleaseCompose $Release 'psb-managed' $Release.port @('up','-d','--no-build','--pull','never','--wait','--wait-timeout','90')
    Test-HttpHealth $Release.port | Out-Null
}

function Restore-Pending {
    $pending = Read-State $JournalPath
    if (-not $pending) { return }
    $current = Read-State $StatePath
    if ($current -and $current.sha -eq $pending.candidate.sha) {
        Remove-Item -LiteralPath $JournalPath
        return
    }
    if ($pending.previous) {
        Start-Release $pending.previous
        Write-DeployLog "Rollback restored $($pending.previous.sha)."
    } else {
        Invoke-ReleaseCompose $pending.candidate 'psb-managed' $pending.candidate.port @('down')
        Write-DeployLog 'Failed initial deployment removed.'
    }
    Remove-Item -LiteralPath $JournalPath
}

function Publish-Release([string]$Sha, [int]$ListenPort) {
    if ($Sha -notmatch '\A[0-9a-f]{40}\z') { throw 'Invalid commit SHA.' }
    if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) { throw "Create $EnvFile before deploying." }
    Restore-Pending
    $rejected = Read-State $RejectedPath
    if ($rejected -and $rejected.sha -eq $Sha) {
        Write-DeployLog "Skipping $Sha after a failed activation. Review deployment.log before retrying."
        return
    }
    $prior = Read-State $StatePath
    if ($prior -and $prior.sha -eq $Sha) { Write-DeployLog "Already deployed $Sha."; return }
    if ($prior -and $prior.port -ne $ListenPort) { throw 'Changing the managed port requires an explicit migration.' }
    if ($prior) {
        & git "--git-dir=$Repository" merge-base --is-ancestor $prior.sha $Sha
        if ($LASTEXITCODE -ne 0) { throw 'The candidate does not descend from the installed commit.' }
    }
    Assert-ManagedPort $ListenPort
    $candidate = @{sha = $Sha; port = $ListenPort}
    $folder = Join-Path $ReleaseRoot $Sha
    if (-not (Test-Path -LiteralPath (Join-Path $folder 'compose.yaml'))) {
        $zip = Join-Path $Root "$Sha.zip"
        & git "--git-dir=$Repository" archive --format=zip "--output=$zip" $Sha compose.yaml web prototype organizer/knowledge-base.zip
        if ($LASTEXITCODE -ne 0) { throw 'Could not export the release.' }
        $temporaryFolder = "$folder.$([guid]::NewGuid().ToString('N')).tmp"
        try {
            Expand-Archive -LiteralPath $zip -DestinationPath $temporaryFolder
            [IO.Directory]::Move($temporaryFolder, $folder)
        } finally {
            Remove-Item -LiteralPath $zip
        }
    }
    Write-DeployLog "Staging $Sha."
    try {
        Invoke-ReleaseCompose $candidate 'psb-managed-stage' '0' @('config','--quiet') -Stage
        Invoke-ReleaseCompose $candidate 'psb-managed-stage' '0' @('up','--build','-d','--wait','--wait-timeout','90') -Stage
    } finally {
        Invoke-ReleaseCompose $candidate 'psb-managed-stage' '0' @('down') -Stage
    }
    Write-State $JournalPath @{candidate = $candidate; previous = $prior}
    try {
        Start-Release $candidate
        Write-State $StatePath $candidate
        Remove-Item -LiteralPath $JournalPath
        Write-DeployLog "Active $Sha at http://127.0.0.1:$ListenPort/."
    } catch {
        Write-DeployLog "Activation failed for $Sha. Attempting rollback."
        try { Write-State $RejectedPath @{sha = $Sha} } finally { Restore-Pending }
        throw
    }
}

function Invoke-Locked([scriptblock]$Action, [switch]$StartDesktop) {
    New-Item -ItemType Directory -Path $Root -Force | Out-Null
    $lock = [IO.File]::Open((Join-Path $Root 'deployment.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    try {
        if (-not (Test-Path -LiteralPath $EmptyEnv)) { New-Item -ItemType File -Path $EmptyEnv | Out-Null }
        Assert-Engine -StartDesktop:$StartDesktop
        & $Action
    } catch {
        Write-DeployLog "Failed: $($_.Exception.Message)"
        throw
    } finally {
        $lock.Dispose()
    }
}

function Get-ActiveRelease {
    Restore-Pending
    $release = Read-State $StatePath
    if (-not $release) { throw 'No active release. Run update.ps1 first.' }
    return $release
}
