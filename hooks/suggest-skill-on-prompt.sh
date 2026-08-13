#!/usr/bin/env bash
# UserPromptSubmit hook: routes a prompt to the PHASE GATE it is entering.
#
# What this hook does NOT do, deliberately: it does not try to decide whether a
# message is "about Python" or "about TypeScript" or "about an API" and demand
# the matching review skill. That version was measured at 0 for 3 — across three
# consecutive messages it demanded a code review on an explicitly read-only
# audit request, on a message answering audit questions, and on a status report
# containing no code, because it matched the characters `.py` inside filenames.
# A grep over prose cannot tell you what a message is about. It can tell you
# what the author just SAID THEY WERE DOING, which is a different and much
# narrower claim, and it is the only claim the patterns below make:
#
#   "let's design this"     -> you are entering DESIGN
#   "ready to plan"         -> you are entering IMPL-PLANNING
#   "start implementing"    -> you are entering BUILD
#   "shrink this / support  -> you are about to choose a SHAPE, and this
#    a new kind"               framing reliably hides an existing primitive
#
# Each of those is a phase transition the author announced in the imperative,
# and each has a freeze that must already have happened. The gates are a
# cross-prompt BACKSTOP: the same hand-offs are stated as mandatory in the
# author skills and commands, which is the enforcement. This catches the case
# where the transition arrives in a new prompt rather than inside one turn.
#
# Precision discipline for anything added here: match a stated intention, never
# a topic. A hook that fires wrongly does not merely waste a process — it
# teaches you to ignore hooks generally, which is how the correct ones stop
# working.
#
# Silent if no phase transition is announced. Always exits 0.

set -u

input=$(cat)
context=""

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

# Emit (if anything to say). jq -Rs JSON-encodes the message, the same pattern
# apex-primer.sh and suggest-skill-on-edit.sh use: a raw printf with the text
# interpolated can produce invalid JSON the harness then drops SILENTLY, with a
# zero exit — a gate that stops firing and says nothing about it.
if [ -n "$context" ]; then
  printf '%s' "$context" | jq -Rs '{hookSpecificOutput:{hookEventName:"UserPromptSubmit",additionalContext:.}}' 2>/dev/null
fi

exit 0
