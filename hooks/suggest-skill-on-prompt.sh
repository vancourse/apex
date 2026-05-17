#!/usr/bin/env bash
# UserPromptSubmit hook: scans the user's prompt for language / domain
# keywords and injects a reminder to invoke the matching review skill(s).
#
# Silent if no keywords match. Always exits 0.

set -u

input=$(cat)
context=""

# Python — language + common framework keywords.
if echo "$input" | grep -qiE '\.py\b|\bpython\b|\bpytest\b|\bpydantic\b|\bfastapi\b|\basyncio\b|\bsqlalchemy\b'; then
  context="Invoke the apex:python-review skill."
fi

# TypeScript / React — language + common framework keywords.
if echo "$input" | grep -qiE '\.tsx?\b|\btypescript\b|\breact\b|\bzustand\b|\bzod\b|\bplaywright\b'; then
  context="${context:+$context }Invoke the apex:typescript-review skill."
fi

# API surface — endpoint / payload / handler / response-shape keywords.
# Fires during planning, implementation, and review phases.
if echo "$input" | grep -qiE '\bendpoint\b|\bpayload\b|\bhandler\b|\broute(s|r)?\b|\brequest model\b|\bresponse model\b|\bapi design\b|\bapi shape\b|\bapi surface\b|\b/api/\b'; then
  context="${context:+$context }Invoke the apex:api-surface-review skill (runs at planning, implementation, and review — not just review)."
fi

[ -n "$context" ] && printf '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"%s"}}\n' "$context"

exit 0
