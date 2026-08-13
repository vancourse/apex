#!/usr/bin/env bash
# SessionStart hook — record what was already dirty in this worktree before
# this session touched anything.
#
# Why this exists: `hooks/suggest-review-on-stop.sh` measures "your
# uncommitted code edits" as `git diff HEAD` plus untracked files at the repo
# root. In a worktree shared by concurrent sessions that is everyone's edits,
# not yours — it charged one session 573 lines it had not written, and a nudge
# that is wrong every time it fires is a nudge you learn to dismiss on sight.
# The Stop hook subtracts this snapshot to recover its own contribution.
#
# The snapshot is one line per already-changed path, `<blob-sha><TAB><path>`,
# with `-` standing in for a path that does not exist in the working tree
# (deleted before the session started). Content hashes rather than a status
# list, because a file that was already modified and is modified AGAIN by this
# session must still count: its status stays `M` but its hash moves.
#
# Emits nothing — SessionStart output becomes session context, and this hook
# has nothing to tell the agent. Always exits 0; never blocks a session start.

set -u

input=$(cat)
session_id=$(echo "$input" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$session_id" ] && exit 0

# Same sanitising and same marker directory as suggest-review-on-stop.sh — the
# two files are one mechanism and must agree on where it lives.
safe_session_id="${session_id//[^a-zA-Z0-9_-]/_}"
[ -z "$safe_session_id" ] && exit 0
baseline="${TMPDIR:-/tmp}/apex-session-baseline-${safe_session_id}"

# First SessionStart of the session wins. `clear` and `compact` fire this event
# again with the SAME session_id, and re-snapshotting there would silently
# reclassify everything written before the compaction as somebody else's work.
[ -e "$baseline" ] && exit 0

repo_root=$(git rev-parse --show-toplevel 2>/dev/null)
[ -z "$repo_root" ] && exit 0
cd "$repo_root" || exit 0

# The same two lists the Stop hook builds, so the subtraction lines up exactly.
{
  git diff --name-only HEAD 2>/dev/null
  git ls-files --others --exclude-standard 2>/dev/null
} | sort -u | sed '/^$/d' | while IFS= read -r f; do
  if [ -f "$f" ]; then
    sha=$(git hash-object "$f" 2>/dev/null)
    printf '%s\t%s\n' "${sha:--}" "$f"
  else
    printf -- '-\t%s\n' "$f"
  fi
done > "${baseline}.tmp" 2>/dev/null

# Publish atomically. A Stop firing against a half-written baseline would read
# a truncated file as "the rest is mine" and over-count exactly the way this
# hook exists to prevent.
mv -f "${baseline}.tmp" "$baseline" 2>/dev/null || rm -f "${baseline}.tmp" 2>/dev/null

exit 0
