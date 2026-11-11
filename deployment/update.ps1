[CmdletBinding()]
param(
    [string]$Root = (Join-Path $env:LOCALAPPDATA 'PsbLegalWeb'),
    [ValidateRange(1024,65535)][int]$Port = 8001,
    # Required: an approval of the final PR head by another collaborator.
    # CiOnly: a merged PR into main and green CI are enough (teams without reviews).
    [ValidateSet('Required','CiOnly')][string]$ApprovalPolicy = 'Required',
    [switch]$StartDocker
)
. (Join-Path $PSScriptRoot 'common.ps1')

Invoke-Locked {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'Install and authenticate GitHub CLI for deployment verification.' }
    Restore-Pending
    if (-not (Test-Path -LiteralPath $Repository)) {
        & git init --bare $Repository | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Could not initialize deployment repository.' }
    }
    & git "--git-dir=$Repository" fetch --no-tags $Remote refs/heads/main:refs/heads/reviewed-main
    if ($LASTEXITCODE -ne 0) { throw 'Could not fetch official main.' }
    $sha = & git "--git-dir=$Repository" rev-parse --verify refs/heads/reviewed-main
    if ($LASTEXITCODE -eq 0) { $sha = $sha.Trim() }
    if ($LASTEXITCODE -ne 0 -or $sha -notmatch '\A[0-9a-f]{40}\z') { throw 'Could not resolve main.' }
    $kind = & git "--git-dir=$Repository" cat-file -t $sha
    if ($LASTEXITCODE -ne 0 -or $kind -ne 'commit') { throw 'Official main did not resolve to a commit.' }
    $active = Read-State $StatePath
    if ($active -and $active.sha -eq $sha) { return }

    $pulls = & gh api "repos/$GitHubRepository/commits/$sha/pulls"
    if ($LASTEXITCODE -ne 0) { throw 'Could not verify the associated pull request.' }
    $merged = @((($pulls -join "`n") | ConvertFrom-Json) | Where-Object {
        $_.merged_at -and $_.base.ref -eq 'main' -and $_.merge_commit_sha -eq $sha
    })
    if (-not $merged) { Write-Waiting $sha "$sha has no associated merged PR into main."; return }

    $pr = $merged[0]
    if ($ApprovalPolicy -eq 'Required') {
        $reviews = & gh api "repos/$GitHubRepository/pulls/$($pr.number)/reviews" --paginate --jq '.[] | [.user.login,.state,.commit_id,.author_association] | @tsv'
        if ($LASTEXITCODE -ne 0) { throw 'Could not verify pull request reviews.' }
        $decisions = @{}
        foreach ($review in $reviews) {
            $login, $decision, $commit, $association = $review -split "`t"
            if ($login -ne $pr.user.login -and $association -in @('OWNER','MEMBER','COLLABORATOR') -and
                $decision -in @('APPROVED','CHANGES_REQUESTED','DISMISSED')) {
                $decisions[$login] = ($decision -eq 'APPROVED' -and $commit -eq $pr.head.sha)
            }
        }
        if ($decisions.Values -notcontains $true) {
            Write-Waiting $sha "PR #$($pr.number) has no approval of its final head by another collaborator. Approve it, or install with -ApprovalPolicy CiOnly."
            return
        }
    }

    foreach ($workflow in 'web-ci.yml','security.yml') {
        $json = & gh run list --repo $GitHubRepository --workflow $workflow --branch main --commit $sha --event push --limit 1 --json status,conclusion
        if ($LASTEXITCODE -ne 0) { throw "Could not verify $workflow." }
        $runs = @((($json -join "`n") | ConvertFrom-Json))
        if ($runs.Count -ne 1 -or $runs[0].status -ne 'completed' -or $runs[0].conclusion -ne 'success') {
            Write-Waiting $sha "$workflow has not succeeded for $sha."
            return
        }
    }
    Publish-Release $sha $Port
    if (Test-Path -LiteralPath $WaitingPath) { Remove-Item -LiteralPath $WaitingPath }
} -StartDesktop:$StartDocker
