#!/usr/bin/env bash
# SessionStart hook — inject a brief apex methodology primer at the start
# of any fresh-context moment (new session, /clear, /compact). Tells the
# agent that apex is installed, names the phase pipeline + entry points,
# and points to FLOW.md for the canonical phase × skill matrix.
#
# Why this exists: every other apex hook (suggest-skill-on-prompt,
# suggest-skill-on-edit, suggest-review-on-stop) fires *reactively* on
# user/agent activity. The primer fires *proactively* once per fresh
# context — so the agent knows apex exists before the first prompt arrives,
# instead of discovering it through a keyword-matched skill suggestion that
# may or may not happen on the first turn.
#
# Schema followed: stdout JSON with hookSpecificOutput.additionalContext,
# same pattern as hooks/suggest-skill-on-prompt.sh.

set -u

# Read stdin (event payload) but don't require any specific fields —
# SessionStart payload varies across Claude Code versions; we just need
# the matcher to have fired.
input=$(cat 2>/dev/null || echo "{}")
_=$input  # quiet unused-var warnings

primer='The apex SDLC plugin is installed in this project. apex is a phase-routed methodology that catches common AI-assisted-coding failure modes (jumping to implementation without a plan, taking the first plausible affordance, pure-addition designs, declaring "done" without verification).

PIPELINE (skip phases for trivial fixes):
  SPEC (new feature)  → apex:prd-review (freeze the spec)
  PLAN                → apex:apex-flow §1a recon + §1b adversarial checklist; apex:recon (artifact); apex:design-feature (NEW feature); apex:api-surface-review (new endpoint)
  DESIGN-FREEZE       → apex:design-review (cold adversarial re-pass)
  IMPL-PLAN           → apex:impl-plan-review (layered PR stack, ≤400 LOC/PR)
  IMPLEMENT           → apex:python-review / apex:typescript-review
  VERIFY              → apex:verification-before-completion (prove it works)
  PRE-PR              → apex:ai-pre-review-checklist (8-step robustness gate)
  OPEN PR             → apex:pr-discipline (draft-default, ask-before-push, squash-to-one)
  REVIEW              → apex:copilot-review-loop (GraphQL bot-request mutation; 5-round cap)

TWO-VOICE REVIEW (default for non-trivial work): apex:adversarial-pair — runs any review skill twice in parallel worktree-isolated agents (cooperative steelman + adversarial attacker), reconciles findings.

ENTRY POINTS: /apex:flow (full methodology) or invoke the apex-flow skill in context. Phase × skill matrix lives in FLOW.md.

SKIP FOR: typos, single-line behavior changes, obvious bugs. When in doubt, run the gate.'

# Emit additionalContext using jq to safely encode the primer string.
printf '%s' "$primer" | jq -Rs '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:.}}'
exit 0
