#!/usr/bin/env bash
# Shim: run one of apex's Python hooks, or stay silent when Python is absent.
#
# apex's other hooks are bash + jq. Three are Python instead — they tail JSONL
# transcripts, parse YAML issue forms, and tokenise shell commands with shlex,
# which bash does badly and which has to behave identically on Windows, macOS
# and Linux.
#
# Why this shim exists: apex already depends on jq, but it does NOT guarantee a
# Python interpreter. Registering the .py files directly would make the harness
# report a hook error on every matching tool call in a repo without Python — and
# a PreToolUse hook that errors is exactly the failure the Python hooks' own
# fail-open contract exists to prevent. This resolves an interpreter, and exits 0
# silently when there is none.
#
# Always exits 0. Never blocks a tool call.
set -u

script="${1:-}"
[ -n "$script" ] || exit 0

# Resolved without dirname/pwd so a broken PATH cannot produce stderr noise on
# the way to a silent exit.
here="${CLAUDE_PLUGIN_ROOT:-}"
if [ -n "$here" ]; then
  here="$here/hooks"
else
  here="${BASH_SOURCE[0]%/*}"
fi
target="$here/$script"
[ -f "$target" ] || exit 0

# DEFER TO THE REPO'S OWN COPY. apex ships session_collisions.py and
# artifact_templates.py for repos that have no equivalent; a repo carrying its
# own version of the same file is authoritative, and running both answers one
# question twice.
#
# Measured 2026-08-13 in a repo that has both: the session received TWO collision
# reports at startup — one from the repo's current version, one from apex's fork,
# which had drifted and omitted a whole section. The artifact-template check fired
# twice on every `gh pr create`. Neither copy knew about the other.
#
# The repo's copy wins rather than apex's because the repo's is the one its own
# tests pin and its own contributors edit; apex's is a portable default.
repo_root="${CLAUDE_PROJECT_DIR:-}"
if [ -n "$repo_root" ] && [ -f "$repo_root/.claude/hooks/$script" ]; then
  cat >/dev/null 2>&1
  exit 0
fi

for candidate in python3 python py; do
  if command -v "$candidate" >/dev/null 2>&1; then
    exec "$candidate" "$target"
  fi
done

# No interpreter. Drain stdin so the harness's write to us cannot fail, then
# exit 0 — indistinguishable from a healthy hook with nothing to say, which is
# the correct behaviour for an advisory hook.
cat >/dev/null 2>&1
exit 0
