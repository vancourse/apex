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

# Phase-freeze gates — each author->review->freeze handoff must complete before the NEXT phase.
# A drafted artifact is authored, not frozen; the cold review must run + freeze it first. These
# backstop the mandatory hand-offs in the author skills/commands for the cross-prompt case.

# -> entering DESIGN: the PRD must be prd-reviewed + frozen.
if echo "$input" | grep -qiE '/apex:design\b|\bdesign(ing)? (a|an|the|this|our|my|new)\b|let.?s design|time to design|start(ing)? (the )?design'; then
  context="${context:+$context }Before apex:design-feature, ensure the PRD is FROZEN via apex:prd-review — a drafted PRD is authored, not frozen. AND if this change is non-trivial or in an unfamiliar / scope-heavy area, run apex:recon first to put existing primitives, contracts, and invariants on the table (skip recon for trivial or familiar work). On a large/unfamiliar repo, recon should query a code graph (Graphify / Serena / Claude Context) rather than grep blind — build one via /apex:setup if none exists; treat it as ephemeral, not the source of truth."
fi

# -> entering IMPL-PLANNING: the design must be design-reviewed + frozen.
if echo "$input" | grep -qiE 'impl(ementation)?[- ]?plan|design (is )?(done|finished|complete|frozen)|ready to plan'; then
  context="${context:+$context }Before apex:impl-plan, ensure apex:design-review has run + FROZEN the design (the cold adversarial re-pass, separate from design-feature's inline counter-passes). A design-feature draft is authored, not frozen."
fi

# -> entering BUILD/CODE: the impl plan must be impl-plan-reviewed + frozen.
if echo "$input" | grep -qiE 'start (implement|build|cod)(ing)?|begin (implement|cod)(ing)?|ready to (implement|build|code)|time to (build|code|implement)|write the code|start coding'; then
  context="${context:+$context }Before implementation/coding, ensure apex:impl-plan-review has run + FROZEN the implementation plan (layered PR stack, sequencing, per-layer tests, rollout, reversibility). A drafted implementation plan is authored, not frozen."
fi

[ -n "$context" ] && printf '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"%s"}}\n' "$context"

exit 0
