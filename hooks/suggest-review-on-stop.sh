#!/usr/bin/env bash
# Stop hook — when an assistant turn ends with non-trivial uncommitted code
# edits in files that have a matching apex review skill, soft-block the stop
# with a reminder to invoke the review BEFORE finishing.
#
# Design notes:
# - Fires AT MOST ONCE per Claude Code session (keyed by session_id from
#   the hook input). The agent's response to the block is its acknowledgement;
#   the marker prevents the hook from firing again on the same turn or any
#   subsequent Stop in this session.
# - Soft block, not hard block: the agent can comply by running the review,
#   OR can reply explaining the review is unnecessary / already done — either
#   way the stop completes on the next attempt.
# - Threshold: 20+ changed lines. Trivial edits don't trigger the nudge.
# - "Changes" includes both tracked diff vs HEAD AND brand-new untracked
#   language files — new-file work is the most common "review needed" case
#   and `git diff` alone would silently skip it.
# - Skip cases (silent exit 0): no session_id, no git repo, no diff, no
#   matching language files, threshold not met, marker already present.
#
# Schema followed: hooks/format-on-save.sh (stdin JSON, jq parsing) +
# Claude Code Stop hook output schema ({"decision":"block","reason":"..."}).

set -u

input=$(cat)
session_id=$(echo "$input" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$session_id" ] && exit 0

# Sanitize session_id to a safe filename component. Guards against path
# traversal (slashes, ..) or odd characters in the ID corrupting the marker
# location. Keep [A-Za-z0-9_-]; replace everything else with `_`.
safe_session_id="${session_id//[^a-zA-Z0-9_-]/_}"
[ -z "$safe_session_id" ] && exit 0

# Per-session, single-fire marker. New sessions get a fresh session_id so the
# marker key changes automatically — no cleanup needed.
marker_dir="${TMPDIR:-/tmp}"
marker="${marker_dir}/apex-suggest-review-${safe_session_id}"
[ -f "$marker" ] && exit 0

# Anchor to the git repo root (the hook may fire from any CWD).
repo_root=$(git rev-parse --show-toplevel 2>/dev/null)
[ -z "$repo_root" ] && exit 0
cd "$repo_root" || exit 0

# Collect changed files: tracked diff vs HEAD + untracked (new files not
# yet added). `git diff --name-only` MISSES untracked files; new-file work
# is the most common "review needed" scenario, so we must merge both lists.
tracked_files=$(git diff --name-only HEAD 2>/dev/null)
untracked_files=$(git ls-files --others --exclude-standard 2>/dev/null)
diff_files=$(printf '%s\n%s\n' "$tracked_files" "$untracked_files" | sort -u | sed '/^$/d')
[ -z "$diff_files" ] && exit 0

# Count lines: tracked-file insertions+deletions (vs HEAD) plus the total
# line count of untracked language files. (Every line of a brand-new file
# is effectively an "insertion" for review-volume purposes.)
tracked_lines=$(git diff --shortstat HEAD 2>/dev/null | grep -oE '[0-9]+ insertion|[0-9]+ deletion' | grep -oE '[0-9]+' | awk '{s+=$1} END {print s+0}')
untracked_lines=0
if [ -n "$untracked_files" ]; then
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    case "$f" in
      *.py|*.ts|*.tsx)
        if [ -f "$f" ]; then
          n=$(wc -l < "$f" 2>/dev/null | tr -d ' ')
          untracked_lines=$((untracked_lines + ${n:-0}))
        fi
        ;;
    esac
  done <<< "$untracked_files"
fi
diff_lines=$((${tracked_lines:-0} + ${untracked_lines:-0}))
[ "$diff_lines" -lt 20 ] && exit 0

# Map touched file extensions to review skill names.
skills=()
if echo "$diff_files" | grep -qE '\.py$'; then
  skills+=("apex:python-review")
fi
if echo "$diff_files" | grep -qE '\.tsx?$'; then
  skills+=("apex:typescript-review")
fi
[ "${#skills[@]}" -eq 0 ] && exit 0

# Mark fired BEFORE emitting the block — ensures we don't re-prompt if the
# hook is re-invoked between the agent's reply and its next stop attempt.
touch "$marker" 2>/dev/null

# Build the reason string. Use printf to join "apex:python-review +
# apex:typescript-review" — `IFS=" + "; "${skills[*]}"` is buggy (bash only
# uses the FIRST character of IFS when expanding `[*]`, so it would join
# with a space, not " + ").
skill_list=$(printf '%s + ' "${skills[@]}" | sed 's/ + $//')
file_count=$(printf '%s\n' "$diff_files" | wc -l | tr -d ' ')
reason="Before stopping: uncommitted code edits detected (${diff_lines} lines across ${file_count} files, including any new untracked code). Invoke ${skill_list} on the diff before declaring done. If the review was already performed this turn, reply with a one-line acknowledgement and stop — the hook will not fire again this session."

# Emit the soft block. The agent receives the reason and decides how to respond.
printf '{"decision":"block","reason":%s}\n' "$(printf '%s' "$reason" | jq -Rs .)"
exit 0
