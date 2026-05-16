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

# force push to main/master
if echo "$cmd" | grep -qE 'git[[:space:]]+push.*(-f|--force|--force-with-lease).*(main|master)([[:space:]]|$)'; then
  block "force push to main/master"
fi

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
