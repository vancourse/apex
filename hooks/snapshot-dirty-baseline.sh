#!/usr/bin/env bash
# SessionStart hook: record which files were ALREADY dirty when this session
# began, so the Stop hook can tell this session's work from everyone else's.
#
# Why this exists. `suggest-review-on-stop.sh` counts uncommitted changes at the
# repository root to decide whether to nudge for a code review. In a checkout
# used by one session that is exactly right. In a checkout shared by several
# concurrent agent sessions — the normal case in a worktree-per-branch repo where
# several windows sit in the same tree — it counts everybody's edits.
#
# Measured 2026-08-13: a session that had written no Python at all was told
# "uncommitted code edits detected (573 lines across 13 files)" and asked to
# review them. Every one of those lines belonged to three other sessions in the
# same worktree. A nudge that is wrong every time it fires is worse than absent:
# it trains the reader to dismiss the whole class on sight.
#
# The baseline is a plain path list, one per line. Only paths that were ALREADY
# dirty are excluded later, and only while they stay dirty in the same way — a
# file another session had open that this session then edits still counts, which
# is the safe direction for a review nudge.
#
# Always exits 0, writes nothing outside TMPDIR, and stays silent: a SessionStart
# hook that prints becomes noise in every session banner.
set -u

input=$(cat 2>/dev/null || true)

session_id=$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null)
[ -n "$session_id" ] || exit 0

# Same sanitisation as the Stop hook: keep [A-Za-z0-9_-], so a session id with a
# slash or `..` cannot steer the write out of TMPDIR.
safe_session_id="${session_id//[^a-zA-Z0-9_-]/_}"
[ -n "$safe_session_id" ] || exit 0

repo_root=$(git rev-parse --show-toplevel 2>/dev/null)
[ -n "$repo_root" ] || exit 0
cd "$repo_root" 2>/dev/null || exit 0

baseline="${TMPDIR:-/tmp}/apex-dirty-baseline-${safe_session_id}"

# Tracked modifications plus untracked files — the same two sources the Stop
# hook merges, so the two lists are comparable without further normalisation.
{
  git diff --name-only HEAD 2>/dev/null
  git ls-files --others --exclude-standard 2>/dev/null
} | sort -u | sed '/^$/d' > "$baseline" 2>/dev/null || true

exit 0
