# Walkthrough: from an idea to a shipped product or feature

This is the narrative companion to [FLOW.md](FLOW.md). FLOW.md is the reference map
("which skill fires at which phase"); this is the *path* you actually walk, in order,
the first few times you use apex. If you just want the one-screen cheat sheet, run
`/apex:help`.

---

## The mental model (three rules)

Everything in apex follows from three rules. Internalize these and the command list
stops being a list to memorize.

1. **Every artifact has an *author* step and a *review/freeze* step.** A PRD, an
   architecture decision, a feature design, an implementation plan — each one is first
   *written* (steelman / cooperative voice) and then *attacked and frozen* (adversarial
   voice, run cold as a separate step so the two voices don't blur). You never go to the
   next phase against an unfrozen artifact.

2. **A frozen artifact is the contract for the next phase.** A frozen PRD is the input
   to design. A frozen design is the input to the impl plan. A frozen impl plan is the
   input to building. This is why the freeze gates matter: they stop you from pouring
   effort onto a foundation that's still moving.

3. **You only type ~6 commands. The model fires the rest.** Command descriptions are
   tagged **`[USER]`** (you type it at a phase boundary) or **`[AUTO]`** (the model fires
   it automatically based on phase + file paths). You drive the phase transitions; apex
   drives the gates inside each phase.

---

## Where do I start?

Two entry points, depending on what you have.

### A) A brand-new product (greenfield)

```
idea
 └─► PRD               (what are we building, for whom, and how do we know it's done?)
      └─► Architecture (one-time: 7 ADRs — runtime, persistence+tenancy, auth+data class,
           │            observability+deploy, design system, release strategy, threat model)
           └─► feature loop  (design → plan → build → verify → PR → review), repeated per feature
```

Architecture runs **once** at the start of a product and re-runs only when a later
feature can't be served by the frozen architecture (an *amendment*). Don't re-run it
per feature.

### B) A new feature inside an existing product

```
idea
 └─► PRD          (for anything non-trivial)
      └─► feature loop   (design → plan → build → verify → PR → review)
```

You **skip architecture** — it's already frozen. You drop straight into the per-feature
loop. (For genuinely small work you can skip even more — see "When to skip steps" at the
bottom.)

---

## The full path, phase by phase

Each row is one phase. **You type** the `[USER]` command to *enter* the phase; the model
fires the `[AUTO]` skills inside it; the **freeze gate** is what must be true before you
move to the next row.

| # | Phase | You type (`[USER]`) | Fires automatically (`[AUTO]`) | Freeze gate before moving on |
|---|---|---|---|---|
| 1 | **PRD** | `/apex:prd` — chains `superpowers:brainstorming` → `superpowers:writing-plans` | `prd-review` — 7-pass audit + overlap/OSS scans + adversarial counter-pass | PRD frozen: acceptance criteria, testable scenarios (tagged by test layer; compound ones split into use-case one-liners), out-of-scope, success metric all settled |
| 2 | **Architecture** *(greenfield only, once)* | `/apex:arch` — authors 7 ADRs | `adr-review` — 5-element audit per ADR | All 7 ADRs accepted → architecture frozen |
| 3 | **Design** | `/apex:design` — scenarios + MVP + deferrals + integration + failure modes + §6 attack surface | `design-review` (adversarial re-pass + freeze) · `threat-model` · `api-surface-review` (if endpoints) | Design frozen: the buildable shape is locked |
| 4 | **Impl plan** | `/apex:impl-plan` — chains `superpowers:writing-plans` against the frozen design | `impl-plan-review` — 5-pass (layered PR stack ≤400 LOC, sequencing, test-plan-per-layer with scenario/use-case lineage + E2E owners, rollout, reversibility) | Plan frozen: PR stack + per-layer test plan locked |
| 5 | **Build** | *(just describe the task)* | language reviews (`python-review` / `typescript-review`), `api-surface-review`, `postgres-review`, `multi-tenancy`, `protocol-first-workflow`, `polymorphic-type-modeling`, `verify-ports`, `test-strategy` — fired by file paths | Each PR in the stack builds + its tests pass |
| 6 | **Verify** | *(describe, or say "verify")* | `verification-before-completion` — tests + logs + browser for UI | Change is proven to work, not just written |
| 7 | **Pre-PR** | `/apex:review-pr` *(optional, heavy — 6 specialists in parallel)* | `ai-pre-review-checklist` · `test-coverage-audit` · language review · `security-review` (if security-touched) | Self-review clean before a human sees it |
| 8 | **Open PR** | *(say "open the PR")* | `pr-discipline` (draft + ask before push) · `pr-review-primer` · `summarize-changes` | Draft PR open with a reviewer-facing description |
| 9 | **Review** | `/apex:copilot-review` | `responding-to-review` — every blocker → a concrete artifact + diff | NITs-only OR 5 rounds → squash-merge |

> **Catch-all:** unsure which row you're on? Type `/apex:flow` — it carries the
> reconnaissance + adversarial checklist and routes you to the right gate.

**Why some rows have no command in the "You type" column.** Build, Verify, and Open PR are
phases where you just describe the work and the `[AUTO]` skills fire — there's nothing to
*author*, so there's no `[USER]` entry point. Their gates (`verification-before-completion`
for Verify; `pr-discipline` + `pr-review-primer` + `summarize-changes` for Open PR) are
**skills, not commands** — they fire automatically and are deliberately kept out of the
slash menu. **Build** has none on purpose: it's the *absence* of a gate (you write code;
the language / api-surface / postgres review skills fire by file path). The slash menu is
limited to the ~11 entry-point commands you actually drive by hand; to fire any auto skill
manually, just ask for it by name (e.g. "run `verify-ports` on this").

---

## Three things worth knowing early

- **Optional human freeze-review (`/apex:spec-view`).** At the PRD / Architecture /
  Design freeze gates, after the corresponding review skill runs, you can render the
  artifact as a disposable, fully-offline rich-HTML page (freeze-readiness dashboard,
  inline-SVG data-flow / STRIDE / MVP-vs-deferred diagrams, collapsible passes, severity
  badges) so a human can eyeball it before the gate closes. The Markdown stays the single
  source of truth; the HTML is a throwaway view in `tmp/apex-views/` (gitignored, never
  re-ingested). It's a sign-off aid, **not** a substitute for the review skills.

- **The 2-agent pair is the *default* on hard reviews, not an escalation.** For
  the `design-review` and `impl-plan-review` skills on a non-trivial artifact (an impl
  plan with ≥3 PRs or any production-data migration; a design touching auth, payments,
  multi-tenant data, crypto, or any trust-boundary crossing), the cooperative+adversarial
  **pair** (`superpowers:dispatching-parallel-agents` — one agent runs the passes in
  steelman mode, a second in attack mode, findings reconciled before freeze) is the
  default. Single-agent review on a non-trivial artifact is a deviation you must justify
  in the artifact itself.

- **Where TDD lives.** apex does **not** re-implement the red-green loop. The discipline
  of *write a failing test first → watch it fail → minimal code to pass → refactor* lives
  in **`superpowers:test-driven-development`** (install separately). apex's
  `test-strategy` owns the layer *around* that loop: *what* to test (scenarios), *which*
  of the 8 layers each test belongs to, and *what to mock* (mock budget ≤2). Use the
  superpowers loop while implementing; use `apex:test-strategy` to place each resulting
  test and pick its CI tier. To focus on one layer, type `/apex:test <layer>` (e.g.
  `/apex:test unit`, `/apex:test smoke`) — a thin router that surfaces that layer's
  what-to-test + mock budget + CI tier (no argument → the full 8-layer menu).

---

## When to skip steps

The full nine-row path is for a **new feature of real size**. Scale it down honestly:

- **Typo / one-line / pure refactor / debugging an existing bug** — skip SPEC and DESIGN
  entirely. Go straight to Build → Verify → PR. (`apex-flow`'s reconnaissance still helps
  if the bug is non-obvious; debugging discipline lives in
  `superpowers:systematic-debugging`.)
- **Small feature in an existing product** — skip Architecture (already frozen). A short
  PRD or even just a design may be enough; let the size of the change decide.
- **Anything touching auth, payments, multi-tenant data, migrations, or a trust
  boundary** — do **not** skip. Run the full design + review pair; these are exactly the
  branch-shaping concerns the gates exist to catch.

The rule of thumb: **skip phases, never skip the freeze on an artifact you did produce.**
A half-frozen design is worse than no design, because the next phase will treat it as a
contract.

---

## See also

- [`/apex:help`](commands/help.md) — the one-screen cheat sheet (`[USER]` vs `[AUTO]`,
  workflow at a glance)
- [FLOW.md](FLOW.md) — the canonical phase × skill routing map and flowchart
- [README.md](README.md) — what's installed (skills / commands / hooks / rules) and how
  to install it
- [CONTRIBUTING.md](CONTRIBUTING.md) — the PR loop apex runs on itself
