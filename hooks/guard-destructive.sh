#!/usr/bin/env bash
# PreToolUse hook for Bash: block obviously destructive commands.
# Exit 2 blocks the tool call and sends stderr back to Claude.

set -u

input=$(cat)
cmd=$(echo "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)

[ -z "$cmd" ] && exit 0

block() {
  echo "BLOCKED: $1" >&2
  echo "Command: $cmd" >&2
  echo "Ask the user to confirm before proceeding, or use a safer alternative." >&2
  exit 2
}

# rm -rf on root, home, or parent dirs
if echo "$cmd" | grep -qE 'rm[[:space:]]+(-[a-zA-Z]*r[a-zA-Z]*f|-rf|-fr)[[:space:]]+(/|~|\$HOME|\.\.)([[:space:]]|$|/)'; then
  block "rm -rf targeting root, home, or parent directory"
fi

# Inspect each shell segment. A later dangerous push must not be hidden behind
# a safe first command, while a later `--base main` argument must not trigger it.
default_branch=$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || true)
default_branch=${default_branch#origin/}
if [ -z "$default_branch" ]; then
  if git show-ref --verify --quiet refs/remotes/origin/master; then
    default_branch=master
  else
    default_branch=main
  fi
fi

while IFS= read -r push_cmd; do
  if ! printf '%s\n' "$push_cmd" | grep -qE 'git[[:space:]]+push([[:space:]]|$)' \
    || ! printf '%s\n' "$push_cmd" | grep -qE -- '(^|[[:space:]])(--force-with-lease|--force|-[[:alnum:]]*f[[:alnum:]]*)([=[:space:]]|$)'; then
    continue
  fi

  # Match exact default-branch refs, not names such as feature/main.
  branch_pattern="(^|[[:space:]])\\+?(${default_branch}|master)([[:space:]]|$)|(^|[[:space:]])[^[:space:]]*:\\+?(refs/(heads|remotes/origin)/)?(${default_branch}|master)([[:space:]]|$)|(^|[[:space:]])\\+?refs/(heads|remotes/origin)/(${default_branch}|master)([[:space:]]|$)"
  if printf '%s\n' "$push_cmd" | grep -qE "$branch_pattern"; then
    block "force push to main/master"
  fi

  # Without a refspec, or with source-only HEAD, git pushes current upstream.
  if printf '%s\n' "$push_cmd" | grep -qE 'git[[:space:]]+push([[:space:]]+(-[^[:space:]]+|--[^[:space:]=]+(=[^[:space:]]+)?))*([[:space:]]+[^[:space:]:]+)?[[:space:]]*$' \
    || printf '%s\n' "$push_cmd" | grep -qE 'git[[:space:]]+push([[:space:]]+(-[^[:space:]]+|--[^[:space:]=]+(=[^[:space:]]+)?))*[[:space:]]+[^[:space:]]+[[:space:]]+HEAD[[:space:]]*$'; then
    if [ "$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)" = "$default_branch" ]; then
      block "force push to main/master"
    fi
  fi
done < <(printf '%s\n' "$cmd" | sed -E 's/[;&|]/\n/g')

# hard reset to a remote ref (can nuke local commits)
if echo "$cmd" | grep -qE 'git[[:space:]]+reset[[:space:]]+--hard[[:space:]]+origin'; then
  block "git reset --hard to remote ref"
fi

# writes/deletes targeting .env files
if echo "$cmd" | grep -qE '(rm|mv|>|>>|tee)[[:space:]].*\.env([[:space:]]|$|\.)'; then
  block "modification of .env file"
fi

# skipping commit/push safety flags
if echo "$cmd" | grep -qE 'git[[:space:]]+(commit|push).*--no-verify'; then
  block "--no-verify bypasses pre-commit checks"
fi

exit 0
