---
description: "[USER] Show the apex command cheat sheet — which commands you type vs which I fire automatically, plus the SDLC workflow at a glance"
---

Display the following cheat sheet to the user verbatim, as a code block. Do NOT invoke any other skill, do NOT run any task. Just print and stop:

```
APEX — Which command should I type?

YOU TYPE THESE — the entire /apex: slash menu (13 entry-point commands):
  /apex:flow              Unsure which gate? This routes you (catch-all)
  /apex:prd             Start a new feature → brainstorm + draft PRD
  /apex:arch    System architecture (once at project start)
  /apex:recon                  Reconnaissance brief before design (surface existing primitives + invariants)
  /apex:design         Design a feature (after PRD frozen)
  /apex:impl-plan       Write impl plan (after design frozen)
  /apex:review-pr              Multi-agent pre-PR review (cooperating specialists)
  /apex:copilot-review    Trigger Copilot review on an open PR
  /apex:spec-view              Render PRD/ADR/design as disposable rich HTML for human freeze-review (optional)
  /apex:test [layer]           Focus test-strategy on ONE test layer
  /apex:remember            Capture a lesson / durable project fact
  /apex:help                   This cheat sheet
  /apex:setup                  Install recommended companions + a codebase-graph tool (one-time)

I FIRE THESE AUTOMATICALLY based on phase + file paths (NOT in the slash menu — you don't type them):
  Reviews:    prd-review · adr-review · design-review · impl-plan-review ·
              python-review · typescript-review · api-surface-review ·
              postgres-review · security-review · test-coverage-audit ·
              test-strategy · ai-pre-review-checklist · verification-before-completion ·
              cross-artifact-consistency
  Triggers:   threat-model · observability-review · multi-tenancy ·
              data-migration-review · polymorphic-type-modeling ·
              protocol-first-workflow · verify-ports
  PR phase:   pr-discipline · pr-review-primer · summarize-changes ·
              responding-to-review
  Post-release: incident-retro (run by name after a RESOLVED incident —
              maps the miss to the gate that should have caught it)
  (Want one by hand? Just ask — e.g. "run security-review on this diff".)

WORKFLOW AT A GLANCE:
  PRD       → /apex:prd         → prd-review (auto)   [→ /apex:spec-view for human HTML review]
  Arch      → /apex:arch  → adr-review (auto, per ADR)  [→ /apex:spec-view]
  Recon     → /apex:recon              (surface existing primitives + invariants before designing)
  Design    → /apex:design     → design-review (auto)  [→ /apex:spec-view]
  Plan      → /apex:impl-plan   → impl-plan-review (auto)
  Build     → (just describe the task)    (auto: language reviews, etc.)
  Testing   → /apex:test [unit|integration|smoke|e2e]  (focus ONE layer)
              → test-strategy (auto, full)  → test-coverage-audit (auto, pre-PR)
              (apex = what/which-layer/what-to-mock; the red-green TDD loop itself
               lives in superpowers:test-driven-development — install separately)
  Verify    → (describe / "verify")        (auto: verification-before-completion)
  Pre-PR    → /apex:review-pr              (heavy, optional — 6 specialists in parallel)
  Open PR   → ("open the PR")              (auto: pr-discipline, primer, summarize)
  Review    → /apex:copilot-review    (auto: responding-to-review)

THE SLASH MENU IS INTENTIONALLY SMALL:
  Only the 13 entry-point commands above appear under /apex: — the ones you drive by hand.
  Every review gate (prd-review, design-review, security-review, …) is a SKILL that fires
  automatically by phase + file path; it has no slash command, by design. Ask for any of
  them by name to run a manual pass.

DEEPER DOCS:
  ~/.claude/plugins/cache/apex/apex/<version>/WALKTHROUGH.md  (idea→feature, in order — start here)
  ~/.claude/plugins/cache/apex/apex/<version>/README.md   (full plugin docs)
  ~/.claude/plugins/cache/apex/apex/<version>/FLOW.md     (canonical phase routing)
  ~/.claude/CLAUDE.md §6                              (your personal skill gates)
```
