#!/usr/bin/env bash
# Behaviour of psb-deploy.sh with stub docker/gh/curl/ss and a real local Git
# remote: approval policy, activation, and rollback after a failed activation.
set -Eeuo pipefail
SCRIPT=$(realpath -- "$(dirname -- "${BASH_SOURCE[0]}")/psb-deploy.sh")
WORK=$(mktemp -d)
trap 'rm -rf -- "$WORK"' EXIT
STUBS=$WORK/bin
mkdir -p "$STUBS" "$WORK/remote"

cat > "$STUBS/docker" <<'EOF'
#!/usr/bin/env bash
echo "${WEB_IMAGE:-} $*" >> "$DOCKER_LOG"
case $1 in
    info) echo 27.0 ;;
    compose)
        [[ $2 == version ]] && { echo 2.30; exit 0; }
        if [[ " $* " == *" --project-name psb-managed "* && " $* " == *" up "* && -n ${FAIL_LIVE_IMAGE:-} && ${WEB_IMAGE:-} == *"$FAIL_LIVE_IMAGE" ]]; then
            exit 1
        fi ;;
esac
exit 0
EOF
cat > "$STUBS/gh" <<'EOF'
#!/usr/bin/env bash
case "$*" in
    *"/reviews"*) printf '%b' "${GH_REVIEWS:-}" ;;
    *"/pulls"*) printf '7\tauthor\t%s\n' "${GH_HEAD:-head}" ;;
    *"run list"*"--workflow web-ci.yml"*"--event push"*) printf 'completed\t%s\n' "${GH_WEB_RESULT:-success}" ;;
    *"run list"*) echo "unexpected run list: $*" >&2; exit 1 ;;
esac
EOF
cat > "$STUBS/curl" <<'EOF'
#!/usr/bin/env bash
[[ " $* " == *healthz* ]] && echo '{"status":"ok","documents":21,"fragments":1113}'
exit 0
EOF
printf '#!/usr/bin/env bash\nexit 0\n' > "$STUBS/ss"
chmod +x "$STUBS"/*

commit() {
    echo "$1" > "$WORK/remote/web/version"
    git -C "$WORK/remote" add -A
    git -C "$WORK/remote" -c user.name=t -c user.email=t@example.invalid commit -q -m "$1"
    git -C "$WORK/remote" rev-parse HEAD
}
git -C "$WORK/remote" init -q -b main
mkdir -p "$WORK/remote/web" "$WORK/remote/prototype" "$WORK/remote/organizer"
echo 'services: {}' > "$WORK/remote/compose.yaml"
echo 'pass' > "$WORK/remote/prototype/x.py"
echo 'zip' > "$WORK/remote/organizer/knowledge-base.zip"
FIRST=$(commit first)

export PATH="$STUBS:$PATH" PSB_ROOT=$WORK/root PSB_REMOTE=$WORK/remote PSB_PORT=8001 DOCKER_LOG=$WORK/docker.log
mkdir -p "$PSB_ROOT"
echo 'LLM_API_KEY=test-placeholder' > "$PSB_ROOT/.env"
fail() { echo "FAIL: $*" >&2; exit 1; }

# 1. Approval required and absent: nothing is deployed, the reason is recorded.
"$SCRIPT" update --approval-policy Required >/dev/null
[[ ! -f $PSB_ROOT/active ]] || fail 'deployed without approval'
grep -q "no approval" "$PSB_ROOT/waiting" || fail 'waiting reason not recorded'

# A merged PR whose Web CI on main failed is not deployed. Web CI is the deploy
# gate; the scheduled security scan is not queried at all (the stub rejects it).
GH_WEB_RESULT=failure "$SCRIPT" update --approval-policy CiOnly >/dev/null
[[ ! -f $PSB_ROOT/active ]] || fail 'deployed with failed Web CI'
grep -q 'Web CI has not succeeded' "$PSB_ROOT/waiting" || fail 'Web CI waiting reason not recorded'

# 2. An approval of the final head by another collaborator deploys it.
GH_HEAD=h1 GH_REVIEWS='reviewer\tAPPROVED\th1\tCOLLABORATOR\n' "$SCRIPT" update --approval-policy Required >/dev/null
[[ $(cat "$PSB_ROOT/active") == "$FIRST 8001" ]] || fail 'approved release not active'
[[ ! -f $PSB_ROOT/waiting ]] || fail 'stale waiting reason kept'
grep -q "psb-managed:$FIRST .*--project-name psb-managed-stage.*up --build" "$DOCKER_LOG" || fail 'candidate not staged'
grep -q "psb-managed-stage.*down" "$DOCKER_LOG" || fail 'staged stack not removed'

# 3. A self-approval does not count.
SECOND=$(commit second)
GH_HEAD=h2 GH_REVIEWS='author\tAPPROVED\th2\tOWNER\n' "$SCRIPT" update --approval-policy Required >/dev/null
[[ $(cat "$PSB_ROOT/active") == "$FIRST 8001" ]] || fail 'self-approval deployed'

# 4. CiOnly deploys without approval; a failed activation rolls back and is rejected.
: > "$DOCKER_LOG"
if FAIL_LIVE_IMAGE=$SECOND "$SCRIPT" update --approval-policy CiOnly >/dev/null 2>&1; then fail 'failed activation reported success'; fi
[[ $(cat "$PSB_ROOT/active") == "$FIRST 8001" ]] || fail 'rollback did not keep the previous release'
[[ $(cat "$PSB_ROOT/rejected") == "$SECOND" ]] || fail 'failed release not rejected'
[[ ! -f $PSB_ROOT/pending ]] || fail 'pending journal left behind'
grep -q "psb-managed:$FIRST .*--project-name psb-managed .*up -d --no-build" "$DOCKER_LOG" || fail 'previous release not restarted'
"$SCRIPT" update --approval-policy CiOnly >/dev/null
[[ $(cat "$PSB_ROOT/active") == "$FIRST 8001" ]] || fail 'rejected release retried automatically'

# 5. The staged candidate never receives the model key.
grep -q -- "--env-file $PSB_ROOT/stage.env" "$DOCKER_LOG" || fail 'stage did not use the empty env file'
echo 'psb-deploy.sh: all scenarios passed'
