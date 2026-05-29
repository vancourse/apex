---
description: "[USER] Show the apex command cheat sheet — which commands you type vs which I fire automatically, plus the SDLC workflow at a glance"
---

Display the following cheat sheet to the user verbatim, as a code block. Do NOT invoke any other skill, do NOT run any task. Just print and stop:

```
APEX — Which command should I type?

YOU TYPE THESE (6 commands cover the whole flow):
  /apex:create-prd             Start a new feature → brainstorm + draft PRD
  /apex:architecture-design    System architecture (once at project start)
  /apex:design-feature         Design a feature (after PRD frozen)
  /apex:create-impl-plan       Write impl plan (after design frozen)
  /apex:review-pr              Multi-agent pre-PR review (cooperating specialists)
  /apex:copilot-review-loop    Trigger Copilot review on an open PR
  /apex:spec-view              Render PRD/ADR/design as disposable rich HTML for human freeze-review (optional)

CATCH-ALL:
  /apex:apex-flow              Unsure which gate? This routes you

I FIRE THESE AUTOMATICALLY based on phase + file paths (you don't type them):
  Reviews:    prd-review · adr-review · design-review · impl-plan-review ·
              python-review · typescript-review · api-surface-review ·
              postgres-review · security-review · test-coverage-audit ·
              ai-pre-review-checklist · verification-before-completion
  Triggers:   threat-model · multi-tenancy · polymorphic-type-modeling ·
              protocol-first-workflow · verify-ports · test-strategy
  PR phase:   pr-discipline · pr-review-primer · summarize-changes ·
              responding-to-review
  Memory:     memory-note (also invokable directly when capturing a lesson)

WORKFLOW AT A GLANCE:
  PRD       → /apex:create-prd         → /apex:prd-review (auto)   [→ /apex:spec-view for human HTML review]
  Arch      → /apex:architecture-design  → /apex:adr-review (auto, per ADR)  [→ /apex:spec-view]
  Design    → /apex:design-feature     → /apex:design-review (auto)  [→ /apex:spec-view]
  Plan      → /apex:create-impl-plan   → /apex:impl-plan-review (auto)
  Build     → (just describe the task)    (auto: language reviews, etc.)
  Testing   → /apex:test [unit|integration|smoke|e2e]  (focus ONE layer)
              → /apex:test-strategy (auto, full)  → /apex:test-coverage-audit (auto, pre-PR)
              (apex = what/which-layer/what-to-mock; the red-green TDD loop itself
               lives in superpowers:test-driven-development — install separately)
  Verify    → (describe / "verify")        (auto: verification-before-completion)
  Pre-PR    → /apex:review-pr              (heavy, optional — 6 specialists in parallel)
  Open PR   → ("open the PR")              (auto: pr-discipline, primer, summarize)
  Review    → /apex:copilot-review-loop    (auto: responding-to-review)

DESCRIPTION TAGS in the slash menu:
  [USER]  — type this command yourself when the matching phase begins
  [AUTO]  — I fire it automatically; you can also invoke if you want a manual pass

DEEPER DOCS:
  ~/.claude/plugins/cache/apex/apex/0.1.0/WALKTHROUGH.md  (idea→feature, in order — start here)
  ~/.claude/plugins/cache/apex/apex/0.1.0/README.md   (full plugin docs)
  ~/.claude/plugins/cache/apex/apex/0.1.0/FLOW.md     (canonical phase routing)
  ~/.claude/CLAUDE.md §6                              (your personal skill gates)
```
