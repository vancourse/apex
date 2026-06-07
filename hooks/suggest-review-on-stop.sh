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
# - Skip cases (silent exit 0): no session_id, no git repo, no diff, no
#   matching language files, threshold not met, marker already present.
#
# Schema followed: hooks/format-on-save.sh (stdin JSON, jq parsing) +
# Claude Code Stop hook output schema ({"decision":"block","reason":"..."}).

set -u

input=$(cat)
session_id=$(echo "$input" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$session_id" ] && exit 0

# Per-session, single-fire marker. New sessions get a fresh session_id so the
# marker key changes automatically — no cleanup needed.
marker_dir="${TMPDIR:-/tmp}"
marker="${marker_dir}/apex-suggest-review-${session_id}"
[ -f "$marker" ] && exit 0

# Anchor to the git repo root (the hook may fire from any CWD).
repo_root=$(git rev-parse --show-toplevel 2>/dev/null)
[ -z "$repo_root" ] && exit 0
cd "$repo_root" || exit 0

# Detect uncommitted code edits (staged + unstaged, vs HEAD).
diff_files=$(git diff --name-only HEAD 2>/dev/null)
[ -z "$diff_files" ] && exit 0

# Diff size threshold — don't nudge on tiny edits.
# `git diff --shortstat` outputs e.g. " 3 files changed, 47 insertions(+), 12 deletions(-)"
diff_lines=$(git diff --shortstat HEAD 2>/dev/null | grep -oE '[0-9]+ insertion|[0-9]+ deletion' | grep -oE '[0-9]+' | awk '{s+=$1} END {print s+0}')
[ "${diff_lines:-0}" -lt 20 ] && exit 0

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

# Build the reason string. Single line; the agent renders it in context.
skill_list=$(IFS=" + "; echo "${skills[*]}")
reason="Before stopping: uncommitted code edits detected (${diff_lines} lines across $(echo "$diff_files" | wc -l | tr -d ' ') files). Invoke ${skill_list} on the diff before declaring done. If the review was already performed this turn, reply with a one-line acknowledgement and stop — the hook will not fire again this session."

# Emit the soft block. The agent receives the reason and decides how to respond.
printf '{"decision":"block","reason":%s}\n' "$(printf '%s' "$reason" | jq -Rs .)"
exit 0
