#!/usr/bin/env bash
# Managed PSB web site on Linux: the same policy as deployment/*.ps1.
# Only a merged, checked main is built; the candidate is staged separately,
# activated on a fixed loopback port after health checks, and rolled back on
# failure. Secrets stay in $ROOT/.env, outside Git and the image.
set -Eeuo pipefail
umask 077

usage() {
    cat <<'EOF'
Usage: psb-deploy.sh COMMAND [--root DIR] [--port N] [--approval-policy Required|CiOnly] [--copy-env-from FILE]
Commands:
  install      copy the agent to ROOT, copy .env once, install a systemd user timer (every 10 min)
  update       deploy the newest checked main (merged PR, CI green, approval per policy)
  start|stop|restart|status|healthcheck   manage the active release
Environment equivalents: PSB_ROOT, PSB_PORT, PSB_APPROVAL_POLICY.
EOF
}

COMMAND=${1:-}
[[ -n $COMMAND ]] || { usage; exit 2; }
shift
ROOT=${PSB_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/psb-legal-web}
PORT=${PSB_PORT:-8001}
POLICY=${PSB_APPROVAL_POLICY:-Required}
COPY_ENV_FROM=
while [[ $# -gt 0 ]]; do
    case $1 in
        --root) ROOT=$2; shift 2 ;;
        --port) PORT=$2; shift 2 ;;
        --approval-policy) POLICY=$2; shift 2 ;;
        --copy-env-from) COPY_ENV_FROM=$2; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    esac
done
if ! [[ $PORT =~ ^[0-9]+$ ]] || (( PORT < 1024 || PORT > 65535 )); then
    echo 'Port must be 1024-65535.' >&2
    exit 2
fi
[[ $POLICY == Required || $POLICY == CiOnly ]] || { echo 'Approval policy must be Required or CiOnly.' >&2; exit 2; }

ROOT=$(realpath -m -- "$ROOT")
GITHUB_REPOSITORY=${PSB_GITHUB_REPOSITORY:-Moonwuk/grounded-legal-rag}
REMOTE=${PSB_REMOTE:-https://github.com/$GITHUB_REPOSITORY.git}
REPO=$ROOT/repository.git
ENV_FILE=$ROOT/.env
EMPTY_ENV=$ROOT/stage.env
STATE=$ROOT/active
PENDING=$ROOT/pending
REJECTED=$ROOT/rejected
WAITING=$ROOT/waiting
RELEASES=$ROOT/releases
LOG=$ROOT/deployment.log
PROJECT=psb-managed
STAGE_PROJECT=psb-managed-stage

log() { printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOG"; }
die() { log "Failed: $*"; exit 1; }
valid_sha() { [[ $1 =~ ^[0-9a-f]{40}$ ]]; }

# State files hold one line: "SHA PORT" (pending: "SHA PORT PREVIOUS_SHA PREVIOUS_PORT", "-" for none).
read_line() { [[ -f $1 ]] && head -n 1 -- "$1" || true; }
write_line() { printf '%s\n' "$2" > "$1.tmp" && mv -f -- "$1.tmp" "$1"; }

waiting() {
    # The site keeps the previous release; "status" shows why main is not deployed.
    log "Waiting: $2"
    write_line "$WAITING" "$1 $(date -Is) $2"
}

assert_engine() {
    for tool in docker git curl tar ss; do
        command -v "$tool" >/dev/null || die "Missing dependency: $tool"
    done
    docker compose version --short >/dev/null || die 'Docker Compose is unavailable.'
    docker info --format '{{.ServerVersion}}' >/dev/null 2>&1 || die 'Docker engine is not running.'
}

# compose SHA PROJECT PORT stage|live ARGS... (returns the Compose status; callers decide)
compose() {
    local sha=$1 project=$2 port=$3 mode=$4
    shift 4
    valid_sha "$sha" || { log 'Invalid release SHA.'; return 1; }
    local folder=$RELEASES/$sha env_file=$ENV_FILE
    local -a overrides=(WEB_BIND=127.0.0.1 "WEB_PORT=$port" "WEB_IMAGE=psb-managed:$sha")
    if [[ $mode == stage ]]; then
        # The staged candidate never receives the model key.
        env_file=$EMPTY_ENV
        overrides+=(LLM_BASE_URL= LLM_API_KEY= LLM_MODEL=)
    fi
    env "${overrides[@]}" docker compose --project-name "$project" --project-directory "$folder" \
        --env-file "$env_file" -f "$folder/compose.yaml" "$@"
}

http_health() {
    local body
    body=$(curl -fsS --max-time 5 "http://127.0.0.1:$1/healthz") || return 1
    [[ $body =~ \"status\":\"ok\" && $body =~ \"documents\":[1-9] && $body =~ \"fragments\":[1-9] ]] || return 1
    curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:$1/"
}

assert_managed_port() {
    local port=$1 ids
    ss -Hltn "sport = :$port" | grep -q . || return 0
    ids=$(docker ps --filter "label=com.docker.compose.project=$PROJECT" \
        --filter 'label=com.docker.compose.service=web' --format '{{.ID}}')
    if [[ $(wc -w <<<"$ids") -eq 1 ]] && docker port "$ids" 8000/tcp | grep -qx "127.0.0.1:$port"; then
        return 0
    fi
    die "Port $port is occupied by another service."
}

start_release() {
    assert_managed_port "$2"
    compose "$1" "$PROJECT" "$2" live up -d --no-build --pull never --wait --wait-timeout 90 ||
        die "Release $1 did not start on port $2."
    http_health "$2" || die "Release $1 is unhealthy on port $2."
}

restore_pending() {
    local line cand cport prev pport active
    line=$(read_line "$PENDING")
    [[ -n $line ]] || return 0
    read -r cand cport prev pport <<<"$line"
    active=$(read_line "$STATE")
    if [[ ${active%% *} == "$cand" ]]; then
        rm -f -- "$PENDING"
        return 0
    fi
    if [[ $prev != - ]]; then
        start_release "$prev" "$pport"
        log "Rollback restored $prev."
    else
        compose "$cand" "$PROJECT" "$cport" live down || die 'Could not remove the failed initial deployment.'
        log 'Failed initial deployment removed.'
    fi
    rm -f -- "$PENDING"
}

publish() {
    local sha=$1 port=$2 prior prior_sha prior_port folder tmp
    valid_sha "$sha" || die 'Invalid commit SHA.'
    [[ -f $ENV_FILE ]] || die "Create $ENV_FILE before deploying."
    restore_pending
    if [[ $(read_line "$REJECTED") == "$sha" ]]; then
        log "Skipping $sha after a failed activation. Review $LOG, then delete $REJECTED to retry."
        return 0
    fi
    prior=$(read_line "$STATE")
    read -r prior_sha prior_port <<<"${prior:-- -}"
    [[ $prior_sha == "$sha" ]] && { log "Already deployed $sha."; return 0; }
    if [[ $prior_sha != - ]]; then
        [[ $prior_port == "$port" ]] || die 'Changing the managed port requires an explicit migration.'
        git --git-dir="$REPO" merge-base --is-ancestor "$prior_sha" "$sha" ||
            die 'The candidate does not descend from the installed commit.'
    fi
    assert_managed_port "$port"
    folder=$RELEASES/$sha
    if [[ ! -f $folder/compose.yaml ]]; then
        mkdir -p -- "$RELEASES"
        tmp=$(mktemp -d "$folder.XXXXXX.tmp")
        git --git-dir="$REPO" archive --format=tar "$sha" compose.yaml web prototype organizer/knowledge-base.zip |
            tar -x -C "$tmp" || { rm -rf -- "$tmp"; die 'Could not export the release.'; }
        mv -- "$tmp" "$folder"
    fi
    log "Staging $sha."
    compose "$sha" "$STAGE_PROJECT" 0 stage config --quiet || die "Invalid Compose configuration in $sha."
    # The staged stack is always removed, whether or not it became healthy.
    local staged=0
    compose "$sha" "$STAGE_PROJECT" 0 stage up --build -d --wait --wait-timeout 90 && staged=1
    compose "$sha" "$STAGE_PROJECT" 0 stage down || log 'Warning: could not remove the staged stack.'
    (( staged )) || die "Staging failed for $sha."
    write_line "$PENDING" "$sha $port ${prior_sha} ${prior_port}"
    if ( start_release "$sha" "$port" ); then
        write_line "$STATE" "$sha $port"
        rm -f -- "$PENDING"
        log "Active $sha at http://127.0.0.1:$port/."
    else
        log "Activation failed for $sha. Attempting rollback."
        write_line "$REJECTED" "$sha"
        restore_pending
        die "Activation failed for $sha."
    fi
}

update() {
    command -v gh >/dev/null || die 'Install and authenticate GitHub CLI for deployment verification.'
    restore_pending
    [[ -d $REPO ]] || git init --quiet --bare -- "$REPO" || die 'Could not initialize deployment repository.'
    git --git-dir="$REPO" fetch --quiet --no-tags "$REMOTE" refs/heads/main:refs/heads/reviewed-main ||
        die 'Could not fetch official main.'
    local sha active pr author head reviews approved=0 result runs run gate=
    sha=$(git --git-dir="$REPO" rev-parse --verify refs/heads/reviewed-main) || die 'Could not resolve main.'
    valid_sha "$sha" || die 'Could not resolve main.'
    [[ $(git --git-dir="$REPO" cat-file -t "$sha") == commit ]] || die 'Official main did not resolve to a commit.'
    active=$(read_line "$STATE")
    [[ ${active%% *} == "$sha" ]] && return 0

    read -r pr author head < <(gh api "repos/$GITHUB_REPOSITORY/commits/$sha/pulls" --jq \
        ".[] | select(.merged_at != null and .base.ref == \"main\" and .merge_commit_sha == \"$sha\") | [.number, .user.login, .head.sha] | @tsv" |
        head -n 1) || true
    [[ -n ${pr:-} ]] || { waiting "$sha" "$sha has no associated merged PR into main."; return 0; }

    if [[ $POLICY == Required ]]; then
        declare -A decisions=()
        reviews=$(gh api "repos/$GITHUB_REPOSITORY/pulls/$pr/reviews" --paginate \
            --jq '.[] | [.user.login, .state, .commit_id, .author_association] | @tsv') ||
            die 'Could not verify pull request reviews.'
        local login state commit association
        while IFS=$'\t' read -r login state commit association; do
            [[ -n $login && $login != "$author" ]] || continue
            [[ $association =~ ^(OWNER|MEMBER|COLLABORATOR)$ ]] || continue
            [[ $state =~ ^(APPROVED|CHANGES_REQUESTED|DISMISSED)$ ]] || continue
            [[ $state == APPROVED && $commit == "$head" ]] && decisions[$login]=1 || decisions[$login]=0
        done <<<"$reviews"
        for login in "${!decisions[@]}"; do (( decisions[$login] )) && approved=1; done
        (( approved )) || {
            waiting "$sha" "PR #$pr has no approval of its final head by another collaborator. Approve it, or install with --approval-policy CiOnly."
            return 0
        }
    fi

    result=$(gh run list --repo "$GITHUB_REPOSITORY" --workflow web-ci.yml --branch main --commit "$sha" \
        --event push --limit 1 --json status,conclusion --jq '.[0] | select(.) | [.status,.conclusion] | @tsv') ||
        die 'Could not verify Web CI.'
    [[ $result == $'completed\tsuccess' ]] || { waiting "$sha" "Web CI has not succeeded for $sha."; return 0; }

    runs=$(gh run list --repo "$GITHUB_REPOSITORY" --workflow security.yml --branch main --commit "$sha" \
        --event schedule --limit 5 --json databaseId --jq '.[].databaseId') ||
        die 'Could not list scheduled scans.'
    while IFS= read -r run; do
        [[ -n $run ]] || continue
        gate=$(gh run view "$run" --repo "$GITHUB_REPOSITORY" --json jobs \
            --jq '.jobs[] | select(.name == "Security gate" and .conclusion != "skipped") | [.status,.conclusion] | @tsv') ||
            die "Could not verify scheduled scan $run."
        [[ -n $gate ]] && break
    done <<<"$runs"
    [[ $gate == $'completed\tsuccess' ]] || { waiting "$sha" "Scheduled Security gate has not succeeded for $sha."; return 0; }
    publish "$sha" "$PORT"
    rm -f -- "$WAITING"
}

active_release() {
    restore_pending
    local line
    line=$(read_line "$STATE")
    [[ -n $line ]] || die 'No active release. Run update first.'
    echo "$line"
}

install_agent() {
    local agent=$ROOT/agent unit_dir=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user
    mkdir -p -- "$agent" "$unit_dir"
    install -m 0700 -- "$(realpath -- "${BASH_SOURCE[0]}")" "$agent/psb-deploy.sh"
    if [[ -n $COPY_ENV_FROM && ! -f $ENV_FILE ]]; then
        install -m 0600 -- "$COPY_ENV_FROM" "$ENV_FILE"
    fi
    [[ -f $ENV_FILE ]] || die "Create $ENV_FILE, or supply --copy-env-from for the initial installation."
    cat > "$unit_dir/psb-web-update.service" <<EOF
[Unit]
Description=Deploy the checked PSB web release
After=network-online.target docker.service

[Service]
Type=oneshot
Environment=PSB_ROOT=$ROOT
Environment=PSB_PORT=$PORT
Environment=PSB_APPROVAL_POLICY=$POLICY
ExecStart=$agent/psb-deploy.sh update
TimeoutStartSec=30min
EOF
    cat > "$unit_dir/psb-web-update.timer" <<'EOF'
[Unit]
Description=Check for a new PSB web release every 10 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
Persistent=true

[Install]
WantedBy=timers.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now psb-web-update.timer
    log "Installed the update timer. To run it without an open session: loginctl enable-linger $USER"
}

mkdir -p -- "$ROOT"
[[ $COMMAND == install ]] && { install_agent; exit 0; }
exec 9>"$ROOT/deployment.lock"
flock -n 9 || { echo 'Another deployment command is running.' >&2; exit 1; }
[[ -f $EMPTY_ENV ]] || : > "$EMPTY_ENV"
assert_engine
case $COMMAND in
    update) update ;;
    start) read -r sha port <<<"$(active_release)"; start_release "$sha" "$port"; log "Started http://127.0.0.1:$port/." ;;
    stop) read -r sha port <<<"$(active_release)"; compose "$sha" "$PROJECT" "$port" live stop || die 'Stop failed.'
          log 'Managed site stopped.' ;;
    restart) read -r sha port <<<"$(active_release)"; compose "$sha" "$PROJECT" "$port" live restart || die 'Restart failed.'
             start_release "$sha" "$port"; log 'Managed site restarted and healthy.' ;;
    status) read -r sha port <<<"$(active_release)"; log "Release $sha on port $port."
            line=$(read_line "$WAITING")
            [[ -n $line && ${line%% *} != "$sha" ]] && echo "Newer main ${line%% *} is not deployed: ${line#* * }" >&2
            compose "$sha" "$PROJECT" "$port" live ps -a || true
            http_health "$port" && echo healthy ;;
    healthcheck) read -r sha port <<<"$(read_line "$STATE")"; [[ -n ${sha:-} ]] || die 'No managed release is active.'
                 http_health "$port" ;;
    *) usage; exit 2 ;;
esac
