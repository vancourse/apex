---
description: "[USER] Show the apex command cheat sheet — which commands you type vs which I fire automatically, plus the SDLC workflow at a glance"
---

Display the following cheat sheet to the user verbatim, as a code block. Do NOT invoke any other skill, do NOT run any task. Just print and stop:

```
APEX — Which command should I type?

YOU TYPE THESE — the entire /apex: slash menu (17 entry-point commands):
  /apex:flow              Unsure which gate? This routes you (catch-all)
  /apex:new                    Create a project from scratch (or adopt apex in an existing one)
  /apex:prd             Start a new feature → brainstorm + draft PRD
  /apex:arch    System architecture (once at project start)
  /apex:recon                  Reconnaissance brief before design (surface existing primitives + invariants)
  /apex:design         Design a feature (after PRD frozen)
  /apex:impl-plan       Write impl plan (after design frozen)
  /apex:review-pr              Multi-agent pre-PR review (cooperating specialists)
  /apex:adversarial-pair  Run any review skill as two parallel worktree agents (steelman + attack), reconcile
  /apex:copilot-review    Trigger Copilot review on an open PR
  /apex:spec-view              Render PRD/ADR/design as disposable rich HTML for human freeze-review (optional)
  /apex:test [layer]           Focus test-strategy on ONE test layer
  /apex:remember            Capture a lesson / durable project fact
  /apex:help                   This cheat sheet
  /apex:setup                  Install recommended companions + a codebase-graph tool (one-time)
  /apex:detect-stack           Profile this project's bug-loop tooling → apex.profile.toml (for investigate-bug)
  /apex:release                Cut a release: semver vs diff, changelog, readiness gate, tag→build→publish, bake

I FIRE THESE AUTOMATICALLY based on phase + file paths (NOT in the slash menu — you don't type them):
  Reviews:    prd-review · adr-review · design-review · impl-plan-review ·
              python-review · typescript-review · api-surface-review ·
              postgres-review · security-review · test-coverage-audit ·
              test-strategy · ai-pre-review-checklist · verification-before-completion ·
              cross-artifact-consistency
  Triggers:   threat-model · observability-review · multi-tenancy ·
              data-migration-review · polymorphic-type-modeling ·
              protocol-first-workflow · verify-ports · ui-design-review (user-facing
              UI — five states, WCAG 2.2, the screenshot LOOK-AT-IT loop) ·
              cicd-review (editing .github/workflows / gitlab-ci / Jenkinsfile —
              least-privilege, SHA-pinned actions, OIDC) · deployment-review
              (deploy workflows / IaC / env promotion — rollback before deploy)
  Council:    council-review (by name — three-seat review for the four highest-
              stakes freezes only: arch · auth/payment design · irreversible
              migration · public API. One round; disagreement goes to YOU.)
  PR phase:   pr-discipline · pr-review-primer · summarize-changes ·
              responding-to-review
  Post-release: incident-retro (run by name after a RESOLVED incident —
              maps the miss to the gate that should have caught it)
              autonomous-fix (run by name, or wire its reference template into
              your CI — the rails an unattended bug-fix agent must satisfy:
              fenced input · fail-closed cost · reproduce-first · draft-only)
  Bug loop:   investigate-bug (run by name — stack-adaptive read-only diagnosis;
              routes via apex.profile.toml + reproduces, then hands to
              autonomous-fix's write gate. Run /apex:detect-stack first.)
  (Want one by hand? Just ask — e.g. "run security-review on this diff".)

WORKFLOW AT A GLANCE:
  New proj  → /apex:new                (greenfield scaffold or adopt apex in an existing repo)
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
  Ship      → /apex:release            (semver vs diff → changelog → readiness gate →
                                        tag → build-from-tag → publish → bake watch;
                                        deploys/IaC: deployment-review fires on the diff)

THE SLASH MENU IS INTENTIONALLY SMALL:
  Only the 17 entry-point commands above appear under /apex: — the ones you drive by hand.
  Every review gate (prd-review, design-review, security-review, …) is a SKILL that fires
  automatically by phase + file path; it has no slash command, by design. Ask for any of
  them by name to run a manual pass.

DEEPER DOCS:
  ~/.claude/plugins/cache/apex/apex/<version>/WALKTHROUGH.md  (idea→feature, in order — start here)
  ~/.claude/plugins/cache/apex/apex/<version>/README.md   (full plugin docs)
  ~/.claude/plugins/cache/apex/apex/<version>/FLOW.md     (canonical phase routing)
  ~/.claude/CLAUDE.md §6                              (your personal skill gates)
```
