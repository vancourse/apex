#!/usr/bin/env bash
# PreToolUse hook for Edit|Write.
# Inspects the target file path and injects a one-line skill-gate reminder
# when the path matches:
#   (a) an API-surface / payload / handler shape    → invoke apex:api-surface-review
#   (b) apex's own plugin internals                 → read MAINTAINING.md
#       (detected via .claude-plugin/plugin.json with name "apex" in an
#        ancestor directory + path under skills/ commands/ hooks/ rules/)
#
# Both checks can fire on the same edit (e.g. an api-surface file inside
# apex's own repo) — messages concatenate into one additionalContext line.
#
# Silent for unrelated paths. Always exits 0 — never blocks the edit.

set -u

input=$(cat)
file=$(echo "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

[ -z "$file" ] && exit 0

# --- Detection: is the edited file inside the apex plugin's own repo? ----
# Walk up to the first .claude-plugin/plugin.json; if its "name" field is
# "apex", we're contributing to the plugin (NOT just using it on another
# project). Bounded walk — stops at first plugin.json found or filesystem
# root, whichever comes first.
in_apex=0
dir=$(dirname "$file")
while [ -n "$dir" ] && [ "$dir" != "/" ] && [ "$dir" != "." ]; do
  if [ -f "$dir/.claude-plugin/plugin.json" ]; then
    if grep -q '"name":[[:space:]]*"apex"' "$dir/.claude-plugin/plugin.json" 2>/dev/null; then
      in_apex=1
    fi
    break  # first plugin.json wins — either we're inside apex or another plugin
  fi
  dir=$(dirname "$dir")
done

# --- Build the message(s). Accumulate, emit once. ------------------------
msg=""

# (a) API-surface check — fires regardless of whether we're in apex's own
# repo, because the api-surface-review skill applies to any project.
case "$file" in
  */payloads/*|*/routes/*|*/services/*|*/handlers/*|*/endpoints/*|*/api/*)
    ext="${file##*.}"
    case "$ext" in
      py)
        msg="API-surface path detected (${file##*/}). Before editing, invoke apex:api-surface-review (run all 5 passes against the proposed/current shape) AND apex:python-review. Run BOTH — they are orthogonal."
        ;;
      ts|tsx)
        msg="API-surface path detected (${file##*/}). Before editing, invoke apex:api-surface-review (run all 5 passes against the proposed/current shape) AND apex:typescript-review. Run BOTH — they are orthogonal."
        ;;
      *)
        msg="API-surface path detected (${file##*/}). Before editing, invoke apex:api-surface-review (run all 5 passes against the proposed/current shape)."
        ;;
    esac
    ;;
esac

# (b) apex-internals check — only fires inside apex's own repo, on paths
# that are part of the plugin's contract (skills, commands, hooks, rules).
if [ "$in_apex" = "1" ]; then
  case "$file" in
    */skills/*|*/commands/*|*/hooks/*|*/rules/*)
      maint_msg="Editing apex plugin internals (${file##*/}). Read MAINTAINING.md for maintainer discipline (pair-pattern verification, slash-count grep) before modifying skills/commands/hooks/rules."
      if [ -n "$msg" ]; then
        msg="${msg} ${maint_msg}"
      else
        msg="$maint_msg"
      fi
      ;;
  esac
fi

# --- Emit (if anything to say). -----------------------------------------
if [ -n "$msg" ]; then
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"%s"}}\n' "$msg"
fi

exit 0
