#!/usr/bin/env bash
set -u

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
HOOK="$ROOT/hooks/guard-destructive.sh"

run_hook() {
  local command=$1
  set +e
  printf '%s\n' "$(jq -cn --arg command "$command" '{tool_input:{command:$command}}')" | bash "$HOOK" >/tmp/apex-guard.stdout 2>/tmp/apex-guard.stderr
  local status=$?
  set -e
  return "$status"
}

run_hook_in() {
  local repo=$1 command=$2
  set +e
  (cd "$repo" && printf '%s\n' "$(jq -cn --arg command "$command" '{tool_input:{command:$command}}')" | bash "$HOOK" >/tmp/apex-guard.stdout 2>/tmp/apex-guard.stderr)
  local status=$?
  set -e
  return "$status"
}

assert_blocked() {
  if run_hook "$1"; then
    printf 'expected blocked: %s\n' "$1" >&2
    exit 1
  fi
}

assert_allowed() {
  if ! run_hook "$1"; then
    printf 'expected allowed: %s\n' "$1" >&2
    exit 1
  fi
}

# Explicit default-branch force pushes are blocked from any checkout.
assert_blocked 'git push --force origin main'
assert_blocked 'git push -pf origin main'
assert_blocked 'git push --force origin +main'
assert_blocked 'git push --force origin HEAD:master'
assert_blocked 'git push --force origin HEAD:refs/heads/main'
assert_blocked 'git push --force origin :refs/heads/main'

# Bare pushes are blocked when the current checkout is the default branch.
tmp_repo=$(mktemp -d)
trap 'rm -rf "$tmp_repo"' EXIT
git -C "$tmp_repo" init -q -b main
git -C "$tmp_repo" config user.email test@example.invalid
git -C "$tmp_repo" config user.name test
touch "$tmp_repo/file"
git -C "$tmp_repo" add file
git -C "$tmp_repo" commit -q -m initial
git -C "$tmp_repo" remote add origin https://example.invalid/repo.git
git -C "$tmp_repo" update-ref refs/remotes/origin/main HEAD
git -C "$tmp_repo" symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
if run_hook_in "$tmp_repo" 'git push -f' || run_hook_in "$tmp_repo" 'git push --force origin' || run_hook_in "$tmp_repo" 'git push --force origin HEAD'; then
  printf 'expected bare default-branch push blocked\n' >&2
  exit 1
fi

# Feature branches and mentions in later commands are not force-push targets.
assert_allowed 'git push --force-with-lease origin feature/domain'
assert_allowed 'git push --force origin fix/remain'
assert_allowed 'git push --force origin feature/main'
assert_blocked 'git push --force origin refs/remotes/origin/main'
assert_allowed 'git push --force-with-lease origin feature/x && gh pr edit 36 --base main'
assert_blocked 'git push --force origin feature/x && git push --force origin main'
assert_blocked 'echo safe; git push --force origin main'


printf 'guard-destructive force-push tests passed\n'
