---
name: design-feature
description: Feature-design-from-scratch gate. Distinct from apex-flow §1b (which is generic "design task" critique covering fixes + refactors). Forces concrete user-flow scenarios, MVP cut, deferral list, integration with existing surface, failure modes. Plus internal-product-overlap and OSS-alternatives scans, plus adversarial counter-pass at every step. Fires when designing a new feature (not a fix). Pairs with apex:prd-review (upstream) and apex:api-surface-review (if the feature exposes an API). Keywords: feature design, new feature, MVP, scenarios, design, architecture, technical design doc, TDD doc.
---

# Feature Design (Cold-Start)

The design gate for a NEW feature where the PRD is solid and now you need to translate it into a buildable shape — without locking in premature abstractions, without missing existing primitives in the codebase, without reinventing what OSS solved.

## When to invoke

**Prerequisite (hard gate):** the PRD must be **FROZEN** — i.e. `apex:prd-review` has run and accepted it. A drafted PRD alone is authored, not frozen. If `prd-review` hasn't run, **stop and run it first** — designing against an un-reviewed PRD bakes its gaps (missing scenarios, unstated scope, an ungated success metric) straight into the design.

**Recon first (conditional):** for a **non-trivial** change or an **unfamiliar / scope-heavy** part of the tree, run **`apex:recon`** before designing — it puts the existing primitives, contracts, and invariants on the table so the design reuses what exists instead of reconstructing it. **Skip** recon for trivial or familiar work (its own YAGNI guard). This is the heavy, artifact-producing version of the §1a reconnaissance `apex-flow` already prescribes.

- The PRD passed `apex:prd-review` and now needs a design
- You're proposing a new service, model, UI surface, or workflow that doesn't already exist
- "Let's design feature X" — that's this skill's signal

**Distinct from:**

- `apex:apex-flow` §1b — generic "design task" adversarial checklist; fires for fixes and refactors too. Use that when the work is *changing* something. Use this skill when the work is *starting* something.
- `apex:api-surface-review` — fires SPECIFICALLY for endpoints/payloads/handlers; run it IN ADDITION to this skill if the feature exposes an API surface (most do).
- `apex:verify-ports` — fires when porting code from another repo, not when designing from scratch.
- `apex:polymorphic-type-modeling` — fires when adding a new variant to an existing discriminated union, not when designing the union itself.

## Adversarial counter-pass — read this first

Every one of the 5 passes below has an **adversarial counter-pass** appended. The counter-pass is not optional; it is the load-bearing half of the review. Run it cold, in a separate cognitive pass — ideally as a second agent (see "Adversarial pair pattern" at the end).

The cooperative half asks *"does this design hold together?"*
The adversarial half asks *"what is this design getting away with?"*

## The 5 passes

### Pass 1 — User-flow scenarios (3-5 concrete)

**Check:** Enumerate the concrete user flows the feature must handle. Each is a "user does X, system shows Y, with edge case Z" sentence. Each becomes one integration test (per `apex:python-review/rules/testing.md` → "Scenarios-First").

**Why:** Designs framed around scenarios stay grounded in user behavior. Designs framed around components drift into architectural abstraction that doesn't match how the feature is actually used. A scenario-anchored design also generates its own test plan.

**Pass condition:** 3-5 scenarios written. Each names a user action, a system response, and at least one edge case (empty state / error state / boundary / permission-denied).

**Adversarial counter-pass:** For each scenario, name a path NOT covered by the listed scenarios. If you find 2+ missing flows, the scenario list is incomplete. Also: name a scenario that the design subtly *can't* handle without architectural rework — those are constraints worth surfacing now, not at implementation time.

### Pass 2 — MVP cut

**Check:** What's the smallest thing that delivers the PRD's acceptance criteria? Everything beyond that is V2.

**Why:** "MVP" is the most-abused word in product. The discipline is to actually NAME the minimal set, not to ship a maximal set and call it minimal. Smaller MVPs ship faster, generate real user feedback sooner, and reduce sunk-cost bias when post-launch data demands a pivot.

**Pass condition:** MVP is described in 5-10 sentences. Anything in the design beyond that is explicitly tagged "V2" or "deferred" (see Pass 3).

**Adversarial counter-pass:** Strike one element from MVP. Does the feature still satisfy the PRD? If yes, the MVP is bloated. Repeat — keep striking until removing any element breaks acceptance. That's the real MVP. Also: name an element you ADDED to MVP that the PRD didn't actually require — scope expansion from "we'll obviously need this" is the most common MVP failure.

### Pass 3 — Deferral list

**Check:** What did we CUT from MVP that has to come back later? Each item with rationale + rough sequencing.

**Why:** A deferral list is the antidote to MVP-as-fig-leaf. It makes the "we'll do this later" promises explicit and trackable. Without it, deferred items vanish — either silently dropped, or rediscovered as bugs.

**Pass condition:** Deferred items are listed with (a) why they're not in MVP, (b) what milestone/condition triggers re-evaluation. ≥3 items if the feature is non-trivial.

**Adversarial counter-pass:** Name something deferred that, if it becomes broken/missing/wrong post-launch, would force a hot fix. Those items don't belong in deferred — they're MVP. Also: name a deferred item whose absence will become obvious within the first 24 hours of launch and embarrass the team. Same conclusion.

### Pass 4 — Integration with existing surface

**Check:** Where does this feature attach to the existing codebase?

- Which services/handlers does it call?
- Which types/models does it extend (vs. introduce new ones)?
- Which UI patterns does it reuse?
- What invariants does it preserve? What does it break?

**Why:** Pure-addition designs are a smell (see `rules/principles.md` §3). A design that doesn't connect to existing primitives either misses reuse opportunities or accidentally violates invariants. Worst case: it parallels an existing system that should have been extended, doubling maintenance forever.

**Pass condition:** ≥2 existing primitives are named that this feature reuses or extends. If everything is new, this feature is either genuinely greenfield (rare) or missing connections. Spell out preserved invariants and called-out broken ones.

**Adversarial counter-pass:** Show me an existing primitive that this design SHOULD extend but instead duplicates. Also: name an invariant of an existing system that this design quietly breaks without acknowledgment (e.g., "all transactions go through service X" — and this design adds a path that bypasses X). Either finding is a real architectural risk.

### Pass 5 — Failure modes

**Check:** How does this feature fail? Cover at minimum:

- **Cold start** — user hits it with empty / no data / first session
- **Empty data** — the table/list/feed has 0 items; the upstream returned `[]`
- **Half-completed state** — operation started, partial state written, user came back; recovery semantics
- **Permission denied** — user lacks the role / tenancy / scope; what do they see?
- **External-dependency failure** — the upstream service is down / slow / returning malformed data
- **Concurrent access** — two requests touch the same state; idempotency + locking story

**Why:** The happy path is 10% of the work. The failure modes are where AI-assisted designs reliably skip — leading to bugs Copilot will find in review (per `apex:python-review/rules/ai-code-smells.md` → "Fake Routing Pattern" and others). Naming failure modes at design time forces decisions before they become incidents.

**Pass condition:** Each failure mode has a stated *user-visible* behavior. "Show empty state with CTA" / "return 403 with a remediation link" / "retry with exponential backoff up to N" / "single-flight gate via Redis lock" / "transaction with `FOR UPDATE` + idempotency key."

**Adversarial counter-pass:** Walk each failure mode and find the one where the design says "throws an error" or "logs and continues" without specifying *user-visible behavior*. Those are unresolved — the implementation will fill them in arbitrarily and the user will see something accidental. Also: name a failure mode not in the list above that this specific feature uniquely exposes (e.g., schema migration mid-rollout, feature-flag flip mid-request, partial CDN cache).

### Pass 6 — Attack surface (invoke `apex:threat-model`)

**Check:** Apply STRIDE to this feature's attack surface, anchored on the trust boundaries + data classification from `apex:architecture-design` Pass 3 (or your equivalent ADR-0003). Run the full **`apex:threat-model`** skill and append its "Threat Model" output to this design doc.

**Why:** Pass 5 covers *operational* failure modes (cold start, empty data, half-state) — what the system does when something goes wrong. Pass 6 covers *adversarial* failure modes — what the system does when someone tries to make something go wrong. They have different mental models, different mitigations, and different reviewers; conflating them buries security in operational concerns.

**Pass condition:** The threat model produces a 6-category output (Spoofing / Tampering / Repudiation / Information disclosure / DoS / Elevation of privilege) with named mitigations OR explicit accepted residual risks per category. `apex:security-review` (PR time) audits the implementation against this output.

**Adversarial counter-pass:** Don't author the threat model yourself in cooperative mode — dispatch the heavier two-agent version via `superpowers:dispatching-parallel-agents` for any feature touching auth, payment, multi-tenant data, admin actions, or cryptography. See `apex:threat-model` for the "when to invoke the heavier pattern" criteria.

## Existing-product overlap scan

Same shape as the PRD-review scan, with an implementation lens:

1. **Grep the codebase** for service / model / route / event-type names that imply the same intent or capability. Use synonyms — "extract / parse / ingest" overlap; "queue / job / task / worker" overlap.
2. **Read the design docs / READMEs** of nearby modules. Sometimes the overlap isn't a feature, it's a *partially-built* feature that was paused.
3. **Ask** — does this feature build a third thing alongside two existing? Does it parallel a path already in the system?

**Pass condition:** The design explicitly states either "no overlap" (with the closest 2 features named + why they're not it) OR "replacing / extending / refactoring X." See `rules/principles.md` §3 (pure-addition smell) and `apex:apex-flow` §1a Q2 (codebase reconnaissance).

**Adversarial counter-pass:** Find an existing feature whose name OR intent is within one synonym of this design. If found and not addressed, the overlap is unaddressed. Also: find a *partial* implementation in the codebase that was abandoned mid-flight — those are the most expensive overlaps to miss because they look like they don't exist until you trip over the orphan tables / dead routes.

## OSS-alternatives scan

For any non-trivial design, look outward before locking in:

1. **Search** for libraries that solve the capability — package managers (PyPI/npm/crates.io/go.dev), GitHub topics, "awesome-X" lists, Hacker News retro threads.
2. **Identify reference implementations** in well-known OSS products. Even when you can't adopt the library, the public source code is free design education for how others handled the same trade-offs.
3. **Decide** — adopt directly / use as design reference / explicitly avoid (with reason).

**Pass condition:** ≥1 OSS alternative or reference implementation considered. Decision + rationale stated. Bonus: link to specific files/functions in the reference implementation that informed your design choices.

**Adversarial counter-pass:** Find an OSS library that solves the core capability and is widely adopted (>1k stars, active maintenance, used in production by recognizable companies). If the design doesn't address it, the scan was incomplete. Common misses: queueing/scheduling, retries/circuit-breaking, telemetry/tracing, feature flags, search, file storage, image processing, rate limiting, A/B testing, auth/RBAC, payment processing.

## Adversarial pair pattern (heavier — for non-trivial designs)

The inline adversarial counter-passes above are the *cheap* version (one agent does both). For non-trivial designs, dispatch the review as **two parallel agents** (see `superpowers:dispatching-parallel-agents`):

- **Cooperative agent** — runs 5 passes + overlap scan + OSS scan in steelman mode. Finds what works, what reuses well, what's clean.
- **Adversarial agent** — runs the same in attack mode. Each adversarial counter-pass becomes the primary lens. Finds the missing scenario, the bloated MVP, the unresolved failure mode, the missed primitive, the un-considered OSS library.

Both agents run in isolated worktrees with the same input design doc. They report independently. Reconcile their findings. Most real design weaknesses surface only when both views are produced and compared.

## Output location

Write the design to **`docs/<feature-slug>/design.md`** — the same per-feature
folder as its `prd.md` (apex's standard layout; the `impl-plan` step will add
`impl-plan.md` beside it). Reuse the slug from the feature's PRD.

## Pass/fail summary

The design passes if:

- All 5 passes meet their pass conditions
- Overlap scan ran and is addressed
- ≥1 OSS alternative was considered
- Adversarial counter-pass findings are addressed or explicitly accepted

Fail any → the design isn't ready for implementation. Reshape before writing code.

## Mandatory next step — `apex:design-review` (do NOT skip)

A `design-feature` draft is **authored, not frozen.** The inline adversarial
counter-passes above are the *cheap* version — a single agent attacking the
design it just authored, with the attack voice contaminated by the just-spent
author voice. The **load-bearing** review is a separate, cold pass:

**Before `apex:impl-plan` or any implementation, run `apex:design-review`.**
It re-walks these 5+1 passes from the attack lens in a separate cognitive step
(ideally a parallel adversarial agent for non-trivial designs) and runs the
**design-freeze ceremony**. Do **not** treat this design as a contract — and do
**not** proceed to impl planning or coding — until `design-review` has run and
**frozen** the design. Skipping it on a non-trivial design is a deviation to
justify explicitly, not a silent default.

## Hand-off to implementation

Once `apex:design-review` has frozen the design, route to the appropriate implementation skills:

- If it exposes an API surface → run `apex:api-surface-review` against the proposed shape before implementing
- If it adds a new variant to an existing union → run `apex:polymorphic-type-modeling`
- If it starts a new Python component → run `apex:protocol-first-workflow`
- For implementation rules → `apex:python-review` / `apex:typescript-review`
- For verification when "done" → `apex:verification-before-completion`
- For pre-PR robustness → `apex:ai-pre-review-checklist`
