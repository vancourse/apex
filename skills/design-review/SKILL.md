---
name: design-review
description: Cold adversarial pass over a spec or design before build: one pass, surviving objections become issues, then build.
---

# Design Review

The gate between "we have a design" and "we have a FROZEN design." Re-walks design-feature's 5+1 passes from the adversarial lens — cold, in a separate cognitive step from authoring — so the steelman voice of the design phase and the attack voice of the review phase don't blur into a single self-congratulatory pass.

## When to invoke

- `rails:design-feature` just produced a design draft and you're about to move to implementation planning
- Before invoking `rails:impl-plan` — impl plans against an un-frozen design are wasted work
- A frozen design needs re-validation (architecture amendment landed; PRD changed)

Pairs with:

- **`rails:design-feature`** (upstream) — authored the design (the steelman pass)
- **`rails:prd-review`** (further upstream) — owns the scenarios this design must satisfy
- **`rails:threat-model`** — owns Pass 6's STRIDE output if the feature has attack surface
- **`rails:impl-plan`** (downstream) — implementation plan against the frozen design
- **`rails:impl-plan-review`** (further downstream) — review of that plan

Distinct from `rails:design-feature`'s inline adversarial counter-passes: those are the cheap version run alongside authoring (same agent, same session — the attack voice contaminated by the just-spent author voice). This skill is the explicit second cognitive pass; for non-trivial designs the heavier *two-attacker* dispatch pattern below (one walking the 6 passes, one running `rails:threat-model`) is the default. See the §"Adversarial pair pattern" section at the bottom for the dispatch mechanics — that pattern is **distinct from `rails:adversarial-pair`'s cooperative+adversarial framing** because `design-review` is itself already the adversarial half of `design-feature`'s authoring voice.

## Adversarial counter-pass — read this first

The review IS the adversarial pass. Run each of the 5+1 passes below in attack mode. The cooperative half is already in the design-feature output; if you can't see it cleanly stated, the design wasn't authored — go back to `rails:design-feature`.

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

Confirm `rails:threat-model` ran and the 6-category STRIDE output (Spoofing / Tampering / Repudiation / Information disclosure / DoS / Elevation of privilege) is appended to the design.

For any feature touching auth, payment, multi-tenant data, admin actions, or cryptography — confirm the **heavier two-agent threat-model** was dispatched (per `rails:threat-model`'s "when to invoke heavier" criteria), not just the cheap inline version. If only the cheap version ran on a heavyweight-criteria feature, fail this pass and dispatch the heavier pattern.

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

After all 6 passes' adversarial findings are addressed (or explicitly accepted with rationale) + scans audited — **mark the design FROZEN.** From this moment on, design changes require a delta amendment (a commit to the design doc), just like PRD amendments. The freeze is what makes `rails:impl-plan` a tractable exercise rather than a moving target.

A frozen design tells the impl-plan author what to build, the test-strategy author what scenarios to mirror, and the threat-model author what surface to defend. None of those downstream skills should be reinventing those decisions.

If the design hasn't passed:

- 1-2 findings → minor revisions, re-run the affected pass
- ≥3 findings or any unresolved failure mode / broken invariant → back to `rails:design-feature`, reshape

### Bound the loop — this ceremony runs at most TWICE for one design

The rule above has no termination condition, and that is a real failure mode, not
a theoretical one. Reshape produces a new design, which earns a new review, which
finds new findings, which triggers reshape. Findings against prose are
**unfalsifiable** — there is no test to settle them — so pass N+1 can always
invent another plausible blocker, and the loop has no fixed point.

Observed cost: one repo's `docs/resource` reached **rev 7 across 71 commits** —
24 review-round commits and 22 reversal/correction commits ("reversed same day",
"residue", "restore") — while the package it described did not exist. The code,
once written, took a day and passed every gate first time.

So:

- **Round 2's surviving findings do not trigger a round 3.** They are filed as
  issues against the implementation and the design freezes with them recorded as
  known-open. Implementation settles them, because code can falsify a claim.
- **A design may be at most one revision ahead of code.** If a design is on rev 3
  with no package in the tree, that is itself the finding — stop reviewing and
  build the thinnest vertical slice that tests the contested decision.
- **The one exception is a stop, not a round 3.** An unresolved trust-boundary
  break or key-custody violation at round 2 means escalate to the owner and hold
  — not another authoring cycle.

This is the artifact-review analog of `rails:copilot-review-loop`'s 5-round cap,
and it carries the same caveat: the cap is about **loop termination, not about
lowering the quality bar.** Surviving findings get *recorded*, not dropped. See
`rails:apex-flow` §12 for the cross-skill rule.

## Adversarial pair pattern (DEFAULT for non-trivial designs)

For a trivial design (no attack surface, single-PR's worth of work, no external input) the inline 6-pass walk above — one agent — is enough. For anything non-trivial — features touching auth, payment, multi-tenant data, cryptography, or any trust-boundary crossing — the pair is **the default, not an escalation.** Dispatch two parallel adversarial agents (Task tool, `isolation: "worktree"`):

- **Adversarial agent A** — walks the 6 passes in attack mode against the design doc.
- **Adversarial agent B** — runs `rails:threat-model` heavyweight pattern independently on the attack surface.

Both run in isolated worktrees with the design doc as input. They report independently. Reconcile their findings. Most real design weaknesses surface only when the attack lens is run separately from the authoring lens and the threat lens is run separately from the architectural lens.

(Note: this is a *two-attacker on different inputs* pair — distinct from `rails:adversarial-pair`'s canonical *cooperative + adversarial on the same input* framing. The dispatch mechanic — parallel Task calls with worktree isolation — is the same; the framings differ because `design-review` is itself already the adversarial half of `design-feature`'s cooperative authoring voice. For non-design artifacts the canonical cooperative+adversarial pair via `rails:adversarial-pair` applies instead.)

Skipping the pair on a non-trivial design is a deviation that must be explicitly justified in the design doc ("single-author review accepted because …"), not a silent default.

## Pass/fail summary

The design is frozen-ready if:

- All 6 adversarial passes' findings are addressed or explicitly accepted
- Overlap + OSS scans audited (no synonym-grade misses, no widely-adopted OSS unaddressed)
- Pass 6 STRIDE output present (or "no attack surface" justified in one line)
- The adversarial pair (now the default for non-trivial designs) was dispatched — or its omission is explicitly justified in the design doc
- **This is review round 1 or 2 for this design** — round 2 is the cap (see §"Bound the loop"). Note the round number in the review output, so the next reviewer knows which round they're on

Fail any → don't freeze. Reshape via `rails:design-feature` before invoking `rails:impl-plan`.

**Unless this was round 2** — then the cap fires instead of a third reshape: freeze the design, record the surviving findings as known-open issues against the implementation, and let code settle them. The one exception is an unresolved trust-boundary break or key-custody violation: escalate to the owner and hold, don't author another round.

## Hand-off

Once frozen:

- **`rails:impl-plan`** — write the implementation plan against the frozen design
- **`rails:impl-plan-review`** — review of that plan (structurally parallel to this skill)
- **`rails:api-surface-review`** — run against the proposed API shape before the impl plan locks endpoint shapes, if the feature exposes an API
- **`rails:polymorphic-type-modeling`** — run if the design adds a new variant to an existing discriminated union
