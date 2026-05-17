#!/usr/bin/env bash
# PreToolUse hook for Edit|Write|MultiEdit.
# Inspects the target file path and injects a one-line skill-gate reminder
# when the path matches an API-surface / payload / handler shape.
#
# Silent for unrelated paths. Always exits 0 — never blocks the edit.

set -u

input=$(cat)
file=$(echo "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

[ -z "$file" ] && exit 0

# Normalize: strip leading slashes so the case patterns are simple.
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
    # PreToolUse additionalContext schema.
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"%s"}}\n' "$msg"
    ;;
esac

exit 0
