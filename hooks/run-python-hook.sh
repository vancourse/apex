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
