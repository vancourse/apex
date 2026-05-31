---
name: design-review
description: Adversarial re-pass + freeze ceremony for a design produced by apex:design-feature. Walks the 5+1 passes from the attack lens, cold, in a separate cognitive step from authoring — so the steelman voice of design and the attack voice of review don't blur into a self-congratulatory pass. Adds explicit design-freeze readiness — the gate between "design drafted" and "implementation plan may begin." Pairs with apex:design-feature (upstream — authors the design) and apex:impl-plan (downstream — frozen design enters impl-plan author step). Fires after design-feature completes, before invoking impl-plan. Keywords: design review, design freeze, adversarial design, design audit, design pair review.
---

# Design Review

The gate between "we have a design" and "we have a FROZEN design." Re-walks design-feature's 5+1 passes from the adversarial lens — cold, in a separate cognitive step from authoring — so the steelman voice of the design phase and the attack voice of the review phase don't blur into a single self-congratulatory pass.

## When to invoke

- `apex:design-feature` just produced a design draft and you're about to move to implementation planning
- Before invoking `apex:impl-plan` — impl plans against an un-frozen design are wasted work
- A frozen design needs re-validation (architecture amendment landed; PRD changed)

Pairs with:

- **`apex:design-feature`** (upstream) — authored the design (the steelman pass)
- **`apex:prd-review`** (further upstream) — owns the scenarios this design must satisfy
- **`apex:threat-model`** — owns Pass 6's STRIDE output if the feature has attack surface
- **`apex:impl-plan`** (downstream) — implementation plan against the frozen design
- **`apex:impl-plan-review`** (further downstream) — review of that plan

Distinct from `apex:design-feature`'s inline adversarial counter-passes: those are the cheap version run alongside authoring (same agent, same session — the attack voice contaminated by the just-spent author voice). This skill is the explicit second cognitive pass, ideally dispatched as a parallel adversarial agent for non-trivial designs.

## Adversarial counter-pass — read this first

The review IS the adversarial pass. Run each of the 5+1 passes below in attack mode. The cooperative half is already in the design-feature output; if you can't see it cleanly stated, the design wasn't authored — go back to `apex:design-feature`.

The cooperative half asked: *"does this design hold together?"*
This review asks: *"what is this design getting away with?"*

## The 5+1 passes (adversarial lens)

### Pass 1 — User-flow scenarios

Walk each listed scenario. Then:

- **Name a flow NOT covered** by the listed scenarios. If ≥2 missing flows, the scenario list is incomplete — back to design.
- **Name a scenario the design subtly *can't* handle without architectural rework.** Surface as a constraint now, not at impl time.

**Pass condition:** every named missing flow is either added to the design or explicitly accepted (with rationale) as out of scope for this iteration.

### Pass 2 — MVP cut

- **Strike one element from MVP. Does the feature still satisfy the PRD?** If yes → MVP is bloated. Repeat until removing any element breaks acceptance — that's the real MVP.
- **Name an element ADDED to MVP that the PRD didn't require.** Scope expansion from "we'll obviously need this" is the most common MVP failure.

**Pass condition:** no strikeable element remains. Anything beyond the irreducible set is tagged V2 / deferred.

### Pass 3 — Deferral list

- **Name a deferred item that, if broken / missing post-launch, would force a hot fix.** Those don't belong in deferred — they're MVP.
- **Name a deferred item whose absence becomes obvious within 24 hours of launch and embarrasses the team.** Same conclusion.

**Pass condition:** no deferred item meets either criterion. Items that do get promoted back into MVP.

### Pass 4 — Integration with existing surface

- **Show an existing primitive this design SHOULD extend but instead duplicates.** Pure-addition is a smell.
- **Name an invariant this design quietly breaks without acknowledgment** ("all transactions go through service X" — and this design adds a path that bypasses X). Either finding is a real architectural risk.

**Pass condition:** each named duplication is either justified ("the existing primitive doesn't generalize") or replaced with an extension. Each named broken invariant is either acknowledged + accepted, or the design is reshaped to preserve it.

### Pass 5 — Failure modes

- **Walk each failure mode and find one where the design says "throws an error" or "logs and continues" without specifying user-visible behavior.** Those are unresolved — the implementation will fill them in arbitrarily and the user will see something accidental.
- **Name a failure mode unique to this feature** not in the design-feature standard list (schema migration mid-rollout, feature-flag flip mid-request, partial CDN cache, mid-deploy version skew, paid-API quota exhaustion).

**Pass condition:** every failure mode has a stated user-visible behavior. The unique-to-this-feature mode is either added to the design or explicitly accepted as a known residual risk.

### Pass 6 — Attack surface

Confirm `apex:threat-model` ran and the 6-category STRIDE output (Spoofing / Tampering / Repudiation / Information disclosure / DoS / Elevation of privilege) is appended to the design.

For any feature touching auth, payment, multi-tenant data, admin actions, or cryptography — confirm the **heavier two-agent threat-model** was dispatched (per `apex:threat-model`'s "when to invoke heavier" criteria), not just the cheap inline version. If only the cheap version ran on a heavyweight-criteria feature, fail this pass and dispatch the heavier pattern.

If the feature has no attack surface, state that explicitly with one-line justification ("internal-only operator tool, no external input, no PII").

**Pass condition:** STRIDE output present with named mitigations or explicit accepted residual risks per category. Heavier pattern dispatched if criteria met.

## Overlap + OSS scans (audit, don't repeat)

The cooperative design-feature pass already ran:

- Internal product-overlap scan
- OSS-alternatives scan (≥1 alternative considered)

Audit, don't re-run. If either is absent or perfunctory, fail and return to design-feature.

**Adversarial spot-check:**

- Name an existing feature whose intent is within one synonym of this design. If found and not addressed in the overlap scan, the scan was incomplete.
- Name a >1k-star OSS library that solves the core capability. If found and not addressed, the scan was incomplete. Common misses: queueing/scheduling, retries/circuit-breaking, telemetry/tracing, feature flags, search, file storage, image processing, rate limiting, A/B testing, auth/RBAC, payment processing.

## Design freeze readiness

After all 6 passes' adversarial findings are addressed (or explicitly accepted with rationale) + scans audited — **mark the design FROZEN.** From this moment on, design changes require a delta amendment (a commit to the design doc), just like PRD amendments. The freeze is what makes `apex:impl-plan` a tractable exercise rather than a moving target.

A frozen design tells the impl-plan author what to build, the test-strategy author what scenarios to mirror, and the threat-model author what surface to defend. None of those downstream skills should be reinventing those decisions.

If the design hasn't passed:

- 1-2 findings → minor revisions, re-run the affected pass
- ≥3 findings or any unresolved failure mode / broken invariant → back to `apex:design-feature`, reshape

## Adversarial pair pattern (DEFAULT for non-trivial designs)

For a trivial design (no attack surface, single-PR's worth of work, no external input) the inline 6-pass walk above — one agent — is enough. For anything non-trivial — features touching auth, payment, multi-tenant data, cryptography, or any trust-boundary crossing — the pair is **the default, not an escalation.** Dispatch two parallel agents via `superpowers:dispatching-parallel-agents`:

- **Adversarial agent A** — walks the 6 passes in attack mode against the design doc.
- **Adversarial agent B** — runs `apex:threat-model` heavyweight pattern independently on the attack surface.

Both run in isolated worktrees with the design doc as input. They report independently. Reconcile their findings. Most real design weaknesses surface only when the attack lens is run separately from the authoring lens and the threat lens is run separately from the architectural lens.

Skipping the pair on a non-trivial design is a deviation that must be explicitly justified in the design doc ("single-author review accepted because …"), not a silent default.

## Pass/fail summary

The design is frozen-ready if:

- All 6 adversarial passes' findings are addressed or explicitly accepted
- Overlap + OSS scans audited (no synonym-grade misses, no widely-adopted OSS unaddressed)
- Pass 6 STRIDE output present (or "no attack surface" justified in one line)
- The adversarial pair (now the default for non-trivial designs) was dispatched — or its omission is explicitly justified in the design doc

Fail any → don't freeze. Reshape via `apex:design-feature` before invoking `apex:impl-plan`.

## Hand-off

Once frozen:

- **`apex:impl-plan`** — write the implementation plan against the frozen design
- **`apex:impl-plan-review`** — review of that plan (structurally parallel to this skill)
- **`apex:api-surface-review`** — run against the proposed API shape before the impl plan locks endpoint shapes, if the feature exposes an API
- **`apex:polymorphic-type-modeling`** — run if the design adds a new variant to an existing discriminated union
