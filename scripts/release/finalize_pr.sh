#!/usr/bin/env bash
set -Eeuo pipefail

if [ "$#" -ne 1 ] || ! [[ "$1" =~ ^[1-9][0-9]*$ ]]; then
  echo "usage: $0 <PR_NUMBER>" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
PR_NUMBER="$1"
SSH_HOST="${W2_SSH_HOST:-}"
SSH_IDENTITY="${W2_SSH_IDENTITY_FILE:-}"
PUBLIC_URL="${W2_PUBLIC_URL:-}"
TIMEOUT_SECONDS="${W2_RELEASE_TIMEOUT_SECONDS:-3600}"
GH_REPO="${W2_GITHUB_REPOSITORY:-QIUYEDALAO/w2-football-intelligence-engine}"
preheat_seconds=0
deploy_seconds=0
rollback=false
deployment=false
result=BLOCKED
source_sha=UNKNOWN
source_tree_sha=UNKNOWN
main_merge_sha=NOT_MERGED
release_run_id=NOT_STARTED
promotion_run_id=NOT_STARTED
full_ci_seconds=0
python_ref=NOT_REQUIRED
web_ref=NOT_REQUIRED
health=NOT_REQUIRED
ready=NOT_REQUIRED
release_sync=NOT_REQUIRED
relay_dir=""
agent_pid=""

cleanup() {
  if [ -n "$relay_dir" ] && [ -d "$relay_dir" ] && [ ! -L "$relay_dir" ]; then
    rm -rf -- "$relay_dir"
  fi
  [ -z "$agent_pid" ] || kill "$agent_pid" >/dev/null 2>&1 || true
}
trap cleanup EXIT

blocked() {
  status=$?
  trap - ERR
  printf '%s\n' \
    "PR_NUMBER=$PR_NUMBER" \
    "SOURCE_SHA=$source_sha" \
    "SOURCE_TREE_SHA=$source_tree_sha" \
    "MAIN_MERGE_SHA=$main_merge_sha" \
    "RELEASE_RUN_ID=$release_run_id" \
    "PROMOTION_RUN_ID=$promotion_run_id" \
    "FULL_CI_WALL_SECONDS=$full_ci_seconds" \
    "PYTHON_IMAGE_DIGEST=${python_ref##*@}" \
    "WEB_IMAGE_DIGEST=${web_ref##*@}" \
    "PREHEAT_SECONDS=$preheat_seconds" \
    "DEPLOY_SWITCH_SECONDS=$deploy_seconds" \
    "HEALTH=$health" \
    "READY=$ready" \
    "RELEASE_SYNC=$release_sync" \
    "ROLLBACK_EXECUTED=$rollback" \
    "DEPLOYMENT_EXECUTED=$deployment" \
    "FINAL_RESULT=BLOCKED"
  exit "$status"
}
trap blocked ERR

wait_check() {
  sha="$1"
  name="$2"
  deadline="$(( $(date +%s) + TIMEOUT_SECONDS ))"
  while [ "$(date +%s)" -lt "$deadline" ]; do
    conclusion="$(GH_REPO="$GH_REPO" gh api "repos/${GH_REPO}/commits/${sha}/check-runs?per_page=100" --jq ".check_runs | map(select(.name == \"${name}\")) | sort_by(.started_at) | last | .conclusion // empty")"
    case "$conclusion" in
      success) return 0 ;;
      failure|cancelled|timed_out|action_required|stale) return 1 ;;
    esac
    sleep 10
  done
  return 1
}

wait_run() {
  workflow="$1"
  sha="$2"
  deadline="$(( $(date +%s) + TIMEOUT_SECONDS ))"
  while [ "$(date +%s)" -lt "$deadline" ]; do
    run_json="$(gh run list --repo "$GH_REPO" --workflow "$workflow" --commit "$sha" --limit 20 --json databaseId,status,conclusion,headSha,createdAt --jq "map(select(.headSha == \"${sha}\")) | sort_by(.createdAt) | last // {}")"
    run_id="$(jq -r '.databaseId // empty' <<<"$run_json")"
    status="$(jq -r '.status // empty' <<<"$run_json")"
    conclusion="$(jq -r '.conclusion // empty' <<<"$run_json")"
    if [ "$status" = completed ]; then
      [ "$conclusion" = success ] || return 1
      printf '%s\n' "$run_id"
      return 0
    fi
    sleep 10
  done
  return 1
}

pr_json="$(gh pr view "$PR_NUMBER" --repo "$GH_REPO" --json state,headRefName,headRefOid,baseRefName,mergeStateStatus)"
test "$(jq -r .state <<<"$pr_json")" = OPEN
test "$(jq -r .baseRefName <<<"$pr_json")" = main
source_branch="$(jq -r .headRefName <<<"$pr_json")"
source_sha="$(jq -r .headRefOid <<<"$pr_json")"
[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]]
wait_check "$source_sha" PR_FAST_REQUIRED

git -C "$ROOT" fetch origin main "$source_branch" --quiet
base_main_sha="$(git -C "$ROOT" rev-parse origin/main)"
git -C "$ROOT" merge-base --is-ancestor "$base_main_sha" "$source_sha" || {
  echo 'RELEASE_CANDIDATE=STALE_BASE' >&2
  exit 1
}
source_tree_sha="$(git -C "$ROOT" rev-parse "${source_sha}^{tree}")"
classification="$(python3 "$ROOT/scripts/classify_ci.py" --base "$base_main_sha" --head "$source_sha")"
deployable="$(sed -n 's/^deployable=//p' <<<"$classification")"
test "$deployable" = true -o "$deployable" = false

triggered_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
release_started="$(date +%s)"
gh workflow run release-candidate.yml --repo "$GH_REPO" --ref "$source_branch" \
  -f "pr_number=$PR_NUMBER" -f "expected_head_sha=$source_sha" \
  -f force_full=true -f "deployable=$deployable" >/dev/null
deadline="$(( $(date +%s) + TIMEOUT_SECONDS ))"
while [ "$(date +%s)" -lt "$deadline" ]; do
  release_run_id="$(gh run list --repo "$GH_REPO" --workflow release-candidate.yml --branch "$source_branch" --event workflow_dispatch --limit 20 --json databaseId,headSha,createdAt --jq "map(select(.headSha == \"${source_sha}\" and .createdAt >= \"${triggered_at}\")) | sort_by(.createdAt) | first | .databaseId // empty")"
  [ -n "$release_run_id" ] && break
  sleep 5
done
test -n "$release_run_id"
gh run watch "$release_run_id" --repo "$GH_REPO" --exit-status >/dev/null
wait_check "$source_sha" RELEASE_REQUIRED
full_ci_seconds="$(( $(date +%s) - release_started ))"

relay_dir="$(mktemp -d "${TMPDIR:-/tmp}/w2-finalize.XXXXXX")"
gh run download "$release_run_id" --repo "$GH_REPO" \
  --name "release-candidate-${source_sha}" --dir "$relay_dir"
manifest="$relay_dir/release-manifest-${source_sha}.json"
manifest_sha="$(python3 "$ROOT/scripts/release_manifest.py" verify --manifest "$manifest" \
  --expect "pr_number=$PR_NUMBER" --expect "source_sha=$source_sha" \
  --expect "source_tree_sha=$source_tree_sha" --expect "base_main_sha=$base_main_sha")"
manifest_deployable="$(jq -r .deployable "$manifest")"
test "$manifest_deployable" = "$deployable"
deployable="$manifest_deployable"
python_ref="$(jq -r .python_image_ref "$manifest")"
web_ref="$(jq -r .web_image_ref "$manifest")"

if [ "$deployable" = true ]; then
  : "${SSH_HOST:?W2_SSH_HOST is required for runtime delivery}"
  : "${SSH_IDENTITY:?W2_SSH_IDENTITY_FILE is required for runtime delivery}"
  : "${PUBLIC_URL:?W2_PUBLIC_URL is required for runtime delivery}"
  test -f "$SSH_IDENTITY"
  preheat_started="$(date +%s)"
  "$ROOT/scripts/relay_immutable_images_via_local.sh" "$SSH_HOST" "$SSH_IDENTITY" "$python_ref" >"$relay_dir/python-relay.log" &
  python_relay_pid=$!
  "$ROOT/scripts/relay_immutable_images_via_local.sh" "$SSH_HOST" "$SSH_IDENTITY" "$web_ref" >"$relay_dir/web-relay.log" &
  web_relay_pid=$!
  wait "$python_relay_pid"
  wait "$web_relay_pid"
  grep -Fx DIGEST_VERIFIED=true "$relay_dir/python-relay.log" >/dev/null
  grep -Fx DIGEST_VERIFIED=true "$relay_dir/web-relay.log" >/dev/null
  preheat_seconds="$(( $(date +%s) - preheat_started ))"
fi

test "$(gh pr view "$PR_NUMBER" --repo "$GH_REPO" --json headRefOid --jq .headRefOid)" = "$source_sha"
test "$(git -C "$ROOT" ls-remote origin refs/heads/main | awk '{print $1}')" = "$base_main_sha"
deadline="$(( $(date +%s) + TIMEOUT_SECONDS ))"
while [ "$(date +%s)" -lt "$deadline" ]; do
  merge_state="$(gh pr view "$PR_NUMBER" --repo "$GH_REPO" --json mergeStateStatus --jq .mergeStateStatus)"
  [ "$merge_state" = CLEAN ] && break
  sleep 5
done
test "${merge_state:-UNKNOWN}" = CLEAN
gh pr merge "$PR_NUMBER" --repo "$GH_REPO" --merge --delete-branch >/dev/null
main_merge_sha=NOT_MERGED
for attempt in $(seq 1 30); do
  main_merge_sha="$(gh pr view "$PR_NUMBER" --repo "$GH_REPO" --json mergeCommit --jq '.mergeCommit.oid // empty')"
  [ -n "$main_merge_sha" ] && break
  sleep 2
done
[[ "$main_merge_sha" =~ ^[0-9a-f]{40}$ ]]
git -C "$ROOT" fetch origin main --quiet
test "$(git -C "$ROOT" rev-parse 'origin/main^{tree}')" = "$source_tree_sha"
promotion_run_id="$(wait_run main-promote.yml "$main_merge_sha")"

health=NOT_REQUIRED
ready=NOT_REQUIRED
release_sync=NOT_REQUIRED
if [ "$deployable" = true ]; then
  eval "$(ssh-agent -s)" >/dev/null
  agent_pid="$SSH_AGENT_PID"
  ssh-add "$SSH_IDENTITY" >/dev/null
  deploy_started="$(date +%s)"
  deploy_output="$(W2_GIT_SHA="$source_sha" "$ROOT/scripts/deploy_stage7h_staging.sh" "$SSH_HOST" "$python_ref" "$web_ref" all)"
  deploy_seconds="$(( $(date +%s) - deploy_started ))"
  grep -q '=PASS duration_seconds=' <<<"$deploy_output"
  grep -q 'rollback=PASS' <<<"$deploy_output" && rollback=true
  curl -fsS --connect-timeout 3 --max-time 8 "$PUBLIC_URL/health" >/dev/null && health=PASS
  curl -fsS --connect-timeout 3 --max-time 8 "$PUBLIC_URL/ready" >/dev/null && ready=PASS
  uv run python "$ROOT/scripts/verify_release_sync.py" --public-url "$PUBLIC_URL" --expected-sha "$source_sha" --allow-empty-data true >/dev/null && release_sync=PASS
  deployment=true
fi

result=PASS
printf '%s\n' \
  "PR_NUMBER=$PR_NUMBER" \
  "SOURCE_SHA=$source_sha" \
  "SOURCE_TREE_SHA=$source_tree_sha" \
  "MAIN_MERGE_SHA=$main_merge_sha" \
  "RELEASE_RUN_ID=$release_run_id" \
  "PROMOTION_RUN_ID=$promotion_run_id" \
  "FULL_CI_WALL_SECONDS=$full_ci_seconds" \
  "PYTHON_IMAGE_DIGEST=${python_ref##*@}" \
  "WEB_IMAGE_DIGEST=${web_ref##*@}" \
  "PREHEAT_SECONDS=$preheat_seconds" \
  "DEPLOY_SWITCH_SECONDS=$deploy_seconds" \
  "HEALTH=$health" \
  "READY=$ready" \
  "RELEASE_SYNC=$release_sync" \
  "ROLLBACK_EXECUTED=$rollback" \
  "DEPLOYMENT_EXECUTED=$deployment" \
  "FINAL_RESULT=$result"

git -C "$ROOT" fetch --prune origin --quiet
git -C "$ROOT" merge-base --is-ancestor "$source_sha" origin/main
source_worktree="$(git -C "$ROOT" worktree list --porcelain | awk -v branch="refs/heads/${source_branch}" '
  /^worktree / { path=substr($0, 10) }
  /^branch / && substr($0, 8) == branch { print path }
')"
if [ -n "$source_worktree" ]; then
  test -z "$(git -C "$source_worktree" status --porcelain)"
  common_dir="$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir)"
  if [ "$source_worktree" = "$ROOT" ]; then
    parent_pid="$$"
    nohup bash -c '
      while kill -0 "$1" 2>/dev/null; do sleep 1; done
      cd /
      git --git-dir="$2" worktree remove --force "$3"
      git --git-dir="$2" branch -D "$4"
      git --git-dir="$2" worktree prune
    ' _ "$parent_pid" "$common_dir" "$source_worktree" "$source_branch" >/dev/null 2>&1 &
  else
    git -C "$ROOT" worktree remove --force "$source_worktree"
    git -C "$ROOT" branch -D "$source_branch"
    git -C "$ROOT" worktree prune
  fi
fi
