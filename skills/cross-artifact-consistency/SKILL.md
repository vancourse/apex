---
name: cross-artifact-consistency
description: Read-only consistency analysis ACROSS a feature's frozen SDLC artifacts — checks that the frozen PRD, design, and impl-plan still AGREE with each other (the horizontal check, distinct from the vertical prd-review / design-review / impl-plan-review which audit each artifact within itself). Builds a traceability matrix over PRD scenarios/use-cases → design elements → impl-plan layers and flags DROPPED scenarios, ORPHAN elements/layers, and CONFLICTs. Authors and freezes nothing; emits a defect list that routes each finding to the upstream gate to re-open. Fires at the impl-plan-freeze boundary, or on demand. Pairs with apex:impl-plan-review (produces the serves-S# lineage it reads), apex:prd-review (owns the scenario IDs), and apex:test-coverage-audit (the spec↔test mirror, which this extends one hop upstream to spec↔design↔plan). Keywords: consistency, cross-artifact, traceability matrix, dropped scenario, orphan layer, conflict, do the frozen artifacts still agree, spec drift, horizontal check.
---

# Cross-Artifact Consistency Analysis

The gate between "each artifact passed its own review" and "the artifacts still
agree with **each other**." `prd-review`, `design-review`, and `impl-plan-review`
each audit one artifact *vertically* and end in a freeze. Nothing checks the
artifacts *horizontally* — that the frozen design still satisfies the frozen PRD,
and the frozen plan covers the frozen design. A scenario silently dropped from
the design, a layer with no upstream anchor, or a success metric the plan never
instruments all pass every vertical gate today. This skill closes that gap.

It is **read-only**: it authors nothing, freezes nothing, and never edits an
artifact. It emits a traceability matrix + a defect list, each finding routed to
the upstream gate to re-open. The matrix is **ephemeral** — regenerated each run
from the frozen markdown, never stored as truth (apex's structural-ephemeral /
semantic-durable split).

## When to invoke

- **At the impl-plan-freeze boundary** (automatic) — once `prd.md`, `design.md`,
  and `impl-plan.md` for a feature are all frozen, before any build, confirm they
  agree. This is the natural firing point.
- **On demand** — "check consistency for `<feature-slug>`", or whenever an
  upstream artifact is amended (re-run to confirm downstream still agrees).
- Run it **in addition to** the vertical reviews, never instead of them.

Do **not** invoke while any of the three artifacts is still a frozen-*candidate*
— consistency against a moving target is meaningless (see Pass 0).

## The procedure

Operate on one feature folder: `docs/<feature-slug>/` (resolve only within that
path — reject a slug containing path separators).

### Pass 0 — Freeze-state precondition

Read the **Status / freeze marker** of `prd.md`, `design.md`, `impl-plan.md`.

- Any artifact still a frozen-*candidate* or marked "drafted" → **STOP** with one
  finding: "`<artifact>` not frozen; freeze it before consistency analysis." No
  partial matrix.
- An artifact **absent** (phase not started) → not an error; report "design phase
  not started for `<slug>`" and analyze only the artifacts that exist.

### Pass 1 — Extract the three node sets

- **Scenarios / use-cases** — from `prd.md` Pass-2 list: the IDs `S1`, `S2`, and
  any decomposed use-cases `S2.1`. Also collect design **failure-modes** and
  **threat-model** entries as valid *ancestors* (a layer can exist to handle a
  failure mode, not only a scenario).
- **Design elements** — `design.md` section headings, plus any `realizes S#`
  tags. A design element with no `realizes` tag and no failure-mode/threat anchor
  is an ORPHAN candidate (the tag is **optional** — untagged self-flags; you are
  never required to add markup).
- **Impl-plan layers** — `impl-plan.md` layers and their `serves S#` lineage
  (`impl-plan-review` Pass 3). Reuse `test-coverage-audit` Pass 1's
  scenario-enumeration logic; do not re-implement scenario parsing.

If `prd.md` has **no scenario IDs** (a pre-traceability PRD) → degrade: "no
scenario IDs found — re-run `prd-review` Pass 2 to enumerate/number scenarios,"
then stop.

### Pass 2 — Build the traceability matrix

One row per scenario/use-case: `scenario → design element(s) → layer(s)`. The
matrix is **1:many / many:1 tolerant** — a scenario may map to several design
elements/layers, and one shared layer may serve several scenarios. Both are fine;
only *zero* on either side is a finding. Render per-scenario rows (never a coarse
"covers all scenarios" collapse — that hides drops).

### Pass 3 — Emit findings

- **DROPPED** — a frozen PRD scenario/use-case with **no** design element *or*
  **no** impl-plan layer owner. (An E2E-tagged scenario present in design but with
  no impl-plan spine-E2E owner is a *partial* drop — reuse `impl-plan-review`
  Pass 3's E2E-owner rule.) → route to `design-review` / `impl-plan-review`.
- **ORPHAN** — a design element or layer with **no** scenario/failure-mode/threat
  ancestor. Gold-plating or undocumented scope. → "amend the PRD, or cut it."
- **CONFLICT** — incompatible claims across artifacts, with both `file:line`
  citations. MVP scope: the **deterministic** cases — (a) a node the PRD marks
  *out-of-scope* that a design/plan node realizes; (b) a `serves S#` that cites a
  scenario the PRD doesn't define. (Free-text "these paragraphs disagree" semantic
  conflict is out of scope — it's a hallucination surface; deterministic only.)

A *resolved* contradiction that cites an amendment ("PRD amended <date> to include
X") is **not** flagged — check the amendment lineage before flagging.

### Pass 4 — Report

Output a markdown report: the matrix, then the findings list. **Each finding names
the upstream gate to re-open** (re-open the PRD / design / impl-plan) — never "fix
it here." Verdict is **CONSISTENT** only when there are zero DROPPED / ORPHAN /
CONFLICT findings.

## Invariants (do not break)

- **Read-only.** Never edit a PRD / design / plan. It reports; a human re-opens the
  upstream gate and amends there (apex's author/review separation).
- **Ephemeral.** The matrix is regenerated each run; it is never committed as a
  source of truth.
- **Additive to the vertical reviews**, not a replacement.

## Attack surface

Reads files by feature slug only. Resolve strictly within `docs/<slug>/` and
**reject any slug containing path separators** (no `../` traversal). No external
input, no network, no PII.

## Pass/fail summary

The feature is consistent if the matrix is complete (every scenario→design→layer
row present) with **zero** DROPPED / ORPHAN / CONFLICT findings. Any finding sends
work back to the named upstream gate before build proceeds.

## Relationship to other skills

- **`test-coverage-audit` Pass 1** — the spec↔*test* mirror. This skill is the same
  mirror discipline extended one hop **upstream** (spec↔design↔plan); it *reuses*
  Pass 1's scenario enumeration rather than forking it.
- **`impl-plan-review` Pass 3** — produces the `serves S#` lineage this reads
  (producer/consumer).
- **`docs/execution-tiers` bead-coverage audit** — the same cardinality model
  (zero-ancestor = orphan, zero-owner = dropped); a candidate shared rule.
