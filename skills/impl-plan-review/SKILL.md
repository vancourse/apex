---
name: impl-plan-review
description: 5-pass review of an implementation plan (how to BUILD it, distinct from apex:design-feature which is what to build). Layered PR stack + sequencing + test-plan-per-layer + rollout strategy + reversibility. Plus inline adversarial counter-pass at every step and a plan-freeze readiness gate at the end. Pairs with superpowers:writing-plans (upstream — writes the plan) and apex:python-review / apex:typescript-review (downstream — implementing against the frozen plan). Fires after design is frozen and before any code is written. Keywords: impl plan, implementation plan, layered PR stack, sequencing, migration order, rollout, feature flag, rollback, reversibility, plan review, plan freeze.
---

# Implementation Plan Review

The gate between "we have a frozen design" and "we can start implementing." Verifies the plan is small-sliced, ordered correctly, has tests with their layers, has a rollout story, and is reversible. Mid-implementation plan changes compound expensively; review the plan before any code is written.

## When to invoke

- `apex:design-feature` (or `apex:apex-flow`) is done and the **design is frozen**
- `superpowers:writing-plans` has produced an implementation plan and it needs review
- Before any code is written for the implementation
- When you have an existing plan and need to confirm it's still sound after a design amendment

Pairs with:

- **`superpowers:writing-plans`** (upstream) — actually writes the implementation plan
- **`apex:design-feature`** (upstream) — owns the design that the plan implements
- **`apex:prd-review`** (further upstream) — owns the scenarios that the plan's tests must mirror
- **`apex:python-review` / `apex:typescript-review`** (downstream) — implementing against the frozen plan
- **`apex:pr-discipline`** §3 — the layered PR stack rule, applied here at the plan-review stage rather than the PR-open stage

## Adversarial counter-pass — read this first

Every pass below has an inline adversarial counter-pass. Run it cold, ideally as a second agent (see "Adversarial pair pattern" at the end).

The cooperative half asks *"does this plan hold together?"*
The adversarial half asks *"what does this plan defer that will bite us?"*

## The 5 passes

### Pass 1 — Layered PR stack

**Check:** Is the plan a STACK of small PRs, each ≤400 hand-written LOC, one architectural layer per PR? Layers typically: types/models → migrations → service/domain → API → frontend. Tests live with their layer, not back-filled.

**Why:** Monolithic implementation = monolithic review = hard to merge, hard to revert. Layered stacks read cleanly per layer, can be rebased independently, and let reviewers approve incrementally. See `apex:pr-discipline` §3 for the canonical rules.

**Pass condition:** Plan names ≥2 (typically 3-5) PRs in the stack. Each has a stated LOC budget + one architectural layer. No PR mixes layers ("a bit of API + a bit of frontend").

**Adversarial counter-pass:** Find a layer with >600 LOC budget or one that mixes concerns. Force the question: can this be split into two? Also: find a layer that *will* exceed 400 LOC once tests are added — those are the layers that secretly mix scopes.

### Pass 2 — Sequencing / dependency order

**Check:** Foundation (types + storage + migrations) before service before API before UI. Cross-cutting concerns (feature flags, telemetry, audit events) inserted at the right layer. Each PR's preconditions are stated.

**Why:** A PR that exposes an API before the migration lands is a recipe for production breakage during rollout. Sequencing makes each layer testable independently and each PR independently reverter-friendly.

**Pass condition:** Each PR in the stack states (a) what shipped PRs it depends on, (b) what downstream PRs in the same stack it unblocks. Dependencies are explicit, not inferred.

**Adversarial counter-pass:** Find a PR that depends on another PR in the stack — does the plan say so? If not, the sequencing is implicit and fragile. Also: find a PR that *could* ship in parallel with its predecessor (because they touch disjoint files) — those are missed optimization opportunities for the stack.

### Pass 3 — Test plan per layer (PRD ↔ integration mirror)

**Check:** Each layer's tests live with the layer. Each layer covers its concerns:

- Foundation layer → unit tests for types / model invariants; migration replay tests
- Service layer → service-class tests with real-ish collaborators (in-memory DB)
- API layer → endpoint tests via test client; contract / shape tests
- Frontend layer → component tests + integration tests through the UI
- **Integration tests across the stack → mirror PRD scenarios 1:1**
- **Scenarios tagged E2E** (`apex:prd-review` Pass 2) → a **spine-E2E browser test** (Playwright, Layer 6) owns each, *in addition to* its integration test. An E2E-tagged scenario covered only at the integration layer is a coverage gap, not a complete plan.

**Why:** Back-filled tests are second-class — they retrofit assumptions. Tests-with-layer means each PR is independently mergeable + verifiable. Integration tests against PRD scenarios are the closing of the spec-to-impl loop (see `apex:prd-review` Pass 2 and `apex:python-review/rules/testing.md` → "PRD ↔ Integration Test Mirror").

**Pass condition:** Each PR in the stack names its test scope **and the PRD scenario(s) — or use-case(s) — it serves** (the layer→scenario lineage — the reverse of the test→scenario map, so every layer's reason-to-exist traces to the spec). Where a scenario was decomposed into sub-numbered use-case one-liners (`apex:prd-review` Pass 2), cite at **use-case granularity** (`serves S2.1, S2.3`) rather than the whole scenario — it makes the many-to-many between vertical scenarios and horizontal layers explicit instead of approximate. Integration tests are explicitly mapped to numbered PRD scenarios/use-cases. Each PRD scenario from `apex:prd-review` Pass 2 has an owner PR in the stack; each **E2E-tagged** scenario additionally has an owner PR for its spine-E2E (Playwright) test.

**Adversarial counter-pass:** Name a PRD scenario that no PR in this stack covers. If found, either a layer needs a test added or the stack is missing a piece of feature surface. Also: name a test that no PRD scenario justifies — that's gold-plating or an undocumented requirement. Also: name an **E2E-tagged scenario whose only owner is an integration test** — the browser-layer coverage the PRD called for is silently missing.

### Pass 4 — Rollout strategy

**Check:** How does each layer ship to production?

- **Feature flag?** (default off, gradual cohort rollout, success-metric tracked per cohort)
- **Direct deploy?** (well-tested, low-risk change, no flag needed)
- **Migration first, code next?** (so old code can still read while new schema is being added)
- **Backwards-compat window?** (for API shape changes that mobile / cached clients will see)
- **Dual-write / read-then-write transition?** (for schema migrations that move data)
- **Expand → migrate → contract** (the discipline for ANY destructive schema change — drop / rename / retype a column, drop a table): split it across **separate PRs** — (1) *Expand*: add the new column/table; app dual-writes old+new, reads old. (2) *Migrate*: backfill as its own step. (3) *Contract*: cut reads to new, then drop the old once nothing references it. Old + new code coexist at every step; each phase is independently deployable **and** revertible. The right question is never "is this migration reversible?" (most useful ones aren't) but "is each *phase* reversible?" (gh-ost / pt-online-schema-change / Fowler's *Parallel Change*).

**Why:** Rollout strategy is where well-tested code still breaks production. A perfectly-implemented feature with no rollout plan is a half-finished feature. PRDs usually mention "launch" but rarely "rollout shape" — the impl plan is where that lives.

**Pass condition:** Each layer's rollout mechanism is stated. If feature-flagged, the flag name + default value + cohort rollout plan + success metric for the cohort are stated. If migration-first, the safe-window during which old + new code can coexist is stated. **No PR drops / renames / retypes a column (or drops a table) in the same PR that ships its code change** — every destructive schema change is decomposed into the expand → migrate → contract phases above, or the plan fails this pass.

**Adversarial counter-pass:** What happens if you ship the API PR but the migration hasn't completed in production yet? If the answer is "it crashes" or "it serves wrong data," the rollout isn't safe — re-sequence or add a forward-compat shim. Also: what's the rollout cohort size for round 1? If "100%", you're not rolling out, you're deploying.

### Pass 5 — Reversibility (rollback story)

**Check:** Can each layer be reverted cleanly? Specifically:

- **Migrations:** is each *phase* independently revertible? A whole destructive migration usually isn't cleanly reversible — which is exactly why Pass 4 decomposes it into expand → migrate → contract. The discipline here is that each phase reverts cleanly and old+new code coexist during the bake window. Flag any single-PR destructive migration (it has no clean revert).
- **Code:** a `git revert` of each PR should leave the system in a coherent state — not "the API references a column that the migration revert just dropped."
- **Feature flags:** can we toggle off without a deploy?
- **Data backfills:** if backfill ran and we revert, is the data left in a valid state? Or is it half-migrated?

**Why:** Reversibility is the difference between "we shipped a bug" and "we shipped a bug for 3 hours then rolled back." Every layer should have a stated rollback path or an explicit "no-rollback, accept the risk" annotation with sign-off.

**Pass condition:** Each layer has a rollback path stated. Irreversible operations (destructive migrations, paid-API one-shots, immutable audit-log writes) are flagged explicitly and either justified or re-sequenced to follow a longer bake-in period.

**Adversarial counter-pass:** Find a layer that's marked rollback-safe but whose revert would actually corrupt state — e.g. data written under new schema that the old code can't read after revert. Also: find a feature flag toggle path that's claimed reversible but actually requires a database migration to undo.

## Plan freeze readiness

After all 5 passes pass + adversarial counter-passes are addressed + overlap with current in-flight work is reconciled — **mark the plan FROZEN**. From this moment on, plan changes require a delta amendment (a commit to the plan doc), just like spec amendments.

A frozen plan tells the implementation phase what to build, in what order, with what tests, with what rollout, with what rollback. The implementer should not be reinventing any of those during coding.

**Circuit breaker (cancel-by-default).** If implementation runs materially past the layered stack this plan projected (Pass 1) — meaningfully more PRs or scope — *without shipping*, the default is to **STOP and re-bet**: return to the design / PRD gate and re-scope, rather than silently extending. Extension is the exception that requires explicit justification, not the default. This is the project-level analog of `copilot-review-loop`'s 5-round cap — it fights sunk-cost bias the same way (a plan that has doubled in size is usually the wrong shape, not merely behind).

## Adversarial pair pattern (heavier — for non-trivial plans)

The inline adversarial counter-passes are the cheap version. For non-trivial plans (≥3 PRs in the stack, or any plan that touches migrations + production data), dispatch the review as **two parallel agents** via `superpowers:dispatching-parallel-agents`:

- **Cooperative agent** — runs the 5 passes in steelman mode. Finds what works, what sequences cleanly, what reverts cleanly.
- **Adversarial agent** — runs the same in attack mode. Each counter-pass becomes the primary lens. Finds the layer that's too big, the dependency that's unstated, the migration that's secretly irreversible.

Both agents run in isolated worktrees with the same input plan. They report independently. Reconcile their findings.

## Pass/fail summary

The plan passes if:

- All 5 passes meet their pass conditions
- Adversarial counter-passes addressed
- Plan is explicitly frozen (or annotated "exploratory, not yet frozen — do not implement against this")

Fail any → revise the plan before any code is written. Mid-implementation plan changes compound expensively; a 1-day plan-review delay saves multi-day implementation rework.

## Hand-off to implementation

Once the plan passes:

- **Layer 1 (foundation)** → start coding it, running `apex:python-review` / `apex:typescript-review` at the implementation phase
- **Each subsequent PR in the stack** → re-run `apex:api-surface-review` if it touches an API surface, re-run `apex:polymorphic-type-modeling` if it adds a discriminated-union variant
- **Pre-PR per layer** → `apex:ai-pre-review-checklist` (9-step robustness gate)
- **Open PR per layer** → `apex:pr-discipline` + `apex:pr-review-primer`
- **Copilot review per layer** → `apex:copilot-review-loop` (GraphQL trigger + 5-round cap)
- **Address reviewer comments** → `apex:responding-to-review`
