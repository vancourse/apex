# Design brief: the rails (agreed with the operator 2026-10-05)

Input to the design workflow (run on Fable, after the evidence workflow `wf_19269310-d69` finishes).

## Goal

A repeatable SDLC process plus an opinionated, best-in-class set of templates that keep
application building on the rails, so apps reach "solid, production strength" faster.
Every layer below must be included and designed. Each layer's deliverable is a check
that can fail wherever possible, not prose.

## Layers (all in scope)

1. **Strong components with strong boundaries.** Contracts (APIs, schemas) enforced by
   machines: one schema source produces the DB tables, API models and typed client;
   contract tests at every seam; a required boot check of the real composition root that
   calls every route and renders every screen once.
2. **A consistent requirements → spec → arch → design → test → validate loop.** Short, with
   the weight on validation: one-page spec with acceptance lines a test could fail, then
   build, then validate against real data, then operator use and acceptance.
3. **Guidelines and templates for building services, database schemas, etc.** Templates as
   code (a starter kit / scaffold that already carries layers 1, 4 and 6), plus the few doc
   templates that earn their place.
4. **Ontology / semantic model layer.** Scoped to domain rules with worked examples as
   operator-reviewed data, checked by a real-data diff against approved answers
   (privacy: real data never enters git).
5. **Catalogue of components already built.** Generated from the code, with reachability
   (zero-caller detection), never hand-maintained.
6. **Scope and done.** WIP limit (one app until it is used); done = the operator used it
   for a real task, not "the demo script passes".
7. **Harness governance.** Every rule, hook and template cites the defects it caught or is
   deleted; a cap on what a session must load.
8. **Enforcement over advice.** Each layer ships as a check that can fail; prose only for
   judgment.

9. **How sessions work with the operator** (added from the transcript analysis, 2026-10-05).
   Invert the ceremony default (35% of operator messages are approvals/push/merge); read intent
   back before the first commit (139 corrections, the largest class); statements need receipts
   (77% of agent self-corrections were wrong statements, 75% had already reached someone);
   "done" is a walk artifact on the named target (83 corrections; only 4 self-catches came from
   looking at a screen); gate the end of a turn (70 stop-early corrections); resolve the
   conflicting rules in one place (push consent vs autonomy, arm-and-stop vs watch CI, one front
   vs finish everything).

## Evidence inputs (all in this scratchpad)

- `evidence.json`: stats, synthesis (`report_markdown`, `coverage_matrix`, `process_requirements`
  PR-01..PR-20, `backtest_cases` x40, `anti_patterns` x26), CI analysis, apex + jarvis-process
  inventories, four doc audits.
- `evidence_report.md`: the evidence synthesis as prose.
- `transcripts_result.json`, `transcripts_report.md`: session analysis. Use the deduplicated
  counts in `transcripts_dedup.json`; the raw counts include 1,145 copied messages.
- Published report: https://claude.ai/artifact/WXnan2MKGNgsCJea7foUoW

## Hard constraints

- Solo developer driving many concurrent AI sessions; every mechanism is priced per PR.
- Windows 11, PowerShell 5.1 and Git Bash: hooks must work on backslash paths and wrap the
  PowerShell tool, and fail open (with a loud notice) when their own script is missing.
- Household financial data never enters git, CI, issue bodies or prompts that leave the box.
- Blocking beats advice; a mechanism that cannot fail is not a mechanism.

## Open question to test with the evidence

Whether building the platform first (38 toolboxes beside 14 apps) contributed: if fixes cluster
at app ↔ platform seams, the process should extract a shared component only when a second
consumer actually exists.

## Method

- Competing drafts (judge panel), each covering all layers.
- Backtest every draft against the synthesis's 30-40 real defects: at which step would it
  have caught each, and at what cost?
- Adversarial pass: would a solo developer with AI agents actually follow this, and what
  does it cost per PR?
- Deliverables: process doc, templates (doc and code), guideline set, governance rules,
  rollout plan for jarvis and for new apps. Proposed home: the apex repo, on a branch,
  not pushed until the operator approves.
