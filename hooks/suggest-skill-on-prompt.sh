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

# Subtractive-design traps — "shrink/bloated PR", "support a new kind/scope/source", "add a flag/field/enum".
# These framings reliably hide an existing primitive and pull toward additive machinery, so nudge
# recon BEFORE a shape is chosen (apex-flow §1a-Q2 codebase recon + §1b-5 pure-addition smell).
if echo "$input" | grep -qiE '\bshrink\b|\bbloated\b|\bslim(mer)?\b|make .*smaller|reduce .*\b(loc|lines)\b|too (big|large)|support (a |an )?new\b|add support for|\bnew (scope|source|kind|variant|field|flag|enum)\b'; then
  context="${context:+$context }Invoke the apex:recon skill BEFORE choosing a design shape — surface the existing primitive that already answers this (apex-flow §1a-Q2) and run the pure-addition / subtractive check (§1b-5) before adding new fields/enums/guards."
fi

# Design-freeze gate — moving from a design toward implementation planning / building.
# A design-feature draft is authored, not frozen; design-review (the cold adversarial re-pass)
# must run + freeze it before create-impl-plan or coding begins. Backstops the mandatory hand-off
# in skills/design-feature/SKILL.md for the case where the move happens in a later prompt.
if echo "$input" | grep -qiE 'impl(ementation)?[- ]?plan|create-impl-plan|start (implement|build|cod)(ing)?|begin (implement|cod)(ing)?|ready to (implement|build|code)|design (is )?(done|finished|complete|frozen)'; then
  context="${context:+$context }Before apex:create-impl-plan or any implementation, ensure apex:design-review has run on the design (the cold adversarial re-pass + design-freeze ceremony, separate from design-feature's inline counter-passes) and FROZEN it. A design-feature draft is authored, not frozen — do not plan or code against an un-reviewed design."
fi

[ -n "$context" ] && printf '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"%s"}}\n' "$context"

exit 0
