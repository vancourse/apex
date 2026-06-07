---
name: prd-review
description: 7-pass review of a Product Requirements Document or product spec — acceptance criteria, testable scenarios enumerated (PRD owns the test list, integration tests mirror 1:1), out-of-scope statement, unknowns named, success metric, sequencing, spec-freeze readiness. Plus internal-product-overlap and OSS-alternatives scans, plus adversarial counter-pass at every step. Fires when reading a new PRD, writing one, or auditing whether a spec is sound enough to freeze and design from. Pairs with superpowers:brainstorming (upstream — explore intent), apex:design-feature (downstream — design the actual feature), apex:impl-plan-review (further downstream — review the build plan), and apex:python-review/rules/testing.md (PRD ↔ Integration Test Mirror). Keywords: PRD, product spec, requirements, acceptance criteria, scenarios, success metric, scope, audit, freeze.
---

# PRD Review

The gate between "we wrote a PRD" and "we can design from this PRD."
Verify the spec is observable, bounded, honest, measurable, and orderable —
and that we're not building something the product already does or that
OSS already solves.

## When to invoke

- Reading a PRD or feature spec written by someone else
- Auditing your own PRD before sending it to design
- When the user asks "is this spec ready?" / "can we design from this?"
- Before `apex:design-feature` — PRD review is its upstream gate

Pairs with:

- **`superpowers:brainstorming`** (upstream) — explores intent before the PRD is even written
- **`apex:design-feature`** (downstream) — designs the actual feature once the PRD is sound
- **`apex:apex-flow` §1c** (sibling) — verifies the customer ask against raw quotes, not writeup interpretations. Run §1c first when you're auditing what was *asked*; run this skill when you're auditing whether the PRD is sound enough to *build from*.

## Adversarial counter-pass — read this first

Every one of the 7 passes below has an **adversarial counter-pass** appended. The counter-pass is not optional; it is the load-bearing half of the review. Run it cold, in a separate cognitive pass — ideally as a second agent (see "Adversarial pair pattern" at the end).

The cooperative half asks *"does this PRD say what it needs to say?"*
The adversarial half asks *"what is this PRD getting away with?"*

## The 7 passes

### Pass 1 — Acceptance criteria: observable, not aspirational

**Check:** Each acceptance criterion is stated in observable terms — "the user can do X", "the system shows Y", "metric Z moves to W". Not "users should feel confident about" or "the experience is polished."

**Why:** Aspirational criteria can't be tested or measured. The PRD becomes a Rorschach test where everyone reads their own success bar into it. Designs that target aspirational criteria drift; designs that target observable criteria converge.

**Pass condition:** Every criterion can become an integration test (see `apex:python-review/rules/testing.md` → "Scenarios-First"). Cite at least one scenario per criterion that would prove it.

**Adversarial counter-pass:** For each criterion, name a path where the criterion is *satisfied* but the user is unhappy / a competitor still beats us / the metric moved for the wrong reason. If you find one, the criterion is under-specified.

### Pass 2 — Testable scenarios enumerated (PRD owns the test list)

**Check:** The PRD includes a list of concrete USER-FLOW SCENARIOS — not just acceptance criteria. Each scenario is "user does X, system shows Y, with edge case Z." The PRD owns this list; **integration tests at implementation time mirror it 1:1**.

**Why:** Acceptance criteria are statements ("the user can do X"). Scenarios are narratives that translate criteria into concrete behavior. Without an explicit scenarios list, the design phase invents scenarios in isolation and integration tests gold-plate. With a PRD-owned scenarios list, the contract is clear: every scenario gets ≥1 integration test, every integration test names its PRD scenario, no orphans on either side. See `apex:python-review/rules/testing.md` → "PRD ↔ Integration Test Mirror" for the impl-side enforcement of this invariant.

**Pass condition:** At least 3 testable scenarios written. Each names a user action, a system response, and at least one edge case (empty / error / boundary / permission-denied / partial-state). Scenarios are numbered or labeled so impl-time tests can reference them by ID.

**Each scenario is tagged with its highest verification layer.** Default is **integration** (`apex:test-strategy` Layer 4 — one test per scenario through `/api/*`). The **critical-path subset** is additionally tagged **E2E** (Layer 6 spine, browser-driven — Playwright per `apex:typescript-review/rules/playwright-e2e.md`). This makes E2E coverage *traceable to scenarios* rather than chosen ad hoc at implementation time — it's the input to `apex:impl-plan-review` Pass 3 (which assigns an owner PR per scenario *and* per E2E tag) and `apex:test-coverage-audit` Pass 1 (which verifies the E2E-tagged scenarios actually got a browser test, not just an integration test). Tag conservatively: most scenarios are integration-only; reserve E2E for the flows whose break would be a launch-blocking, user-visible failure.

**Compound scenarios may break into use-case one-liners (conditional).** A scenario is *vertical* (a user flow); it often bundles several distinct user-visible steps. When — and **only when** — a scenario does more than one user-visible thing, enumerate its steps as **sub-numbered one-liner use-cases** under it: `S2` → `S2.1 user selects and uploads a file` / `S2.2 system rejects an oversized file` / `S2.3 system extracts and displays fields`. A *simple* scenario stays atomic — no sub-numbering (the YAGNI guard; don't manufacture `S-dot` busywork). These one-liners are the finer cross-reference anchor that `apex:impl-plan-review` Pass 3 cites (a layer serves `S2.1, S2.3`, cleaner than a vague "S2") and that `apex:test-coverage-audit` Pass 1 mirrors at the **assertion** level (each use-case → ≥1 named assertion). They are the natural granularity for a bead task in the `docs/execution-tiers` handoff. Format is a one-line sentence each — *not* a full use-case spec (actors / preconditions / alternate flows); that heavier form is deliberately out of scope.

**Adversarial counter-pass:** For each scenario, name a user-visible behavior the scenario doesn't cover but the criteria seem to imply. If 2+ found, the scenario list is missing flows the criteria assume. Also: name a "happy path" scenario that has no paired failure-path counterpart — most happy paths need at least one failure-path companion scenario.

### Pass 3 — Out-of-scope statement

**Check:** The PRD explicitly states what is **NOT** in scope — adjacencies that look related but are deferred, edge cases that won't be handled, integrations that aren't shipping.

**Why:** Without an explicit out-of-scope list, scope creep is inevitable. Anything "obviously" related but not stated will be assumed in-scope by some reader, and shipped by some implementer.

**Pass condition:** At least 3 plausibly-related items are explicitly named out-of-scope, each with one-line rationale ("V2", "blocked on X", "separate team owns it").

**Adversarial counter-pass:** Name something OBVIOUSLY in-scope from the title/intent that isn't in the body. If you find one, either the scope is mis-stated or the in-scope list is incomplete. Also: name something the PRD treats as in-scope that *should be deferred* — feature gravity is real, MVPs balloon.

### Pass 4 — Unknowns named

**Check:** What's still uncertain that the design phase has to resolve? The PRD should NAME these unknowns, not pretend everything is known.

**Why:** Hidden assumptions are the dominant source of design rework. A PRD that confidently asserts everything will mislead designers into locking in choices on unverified premises. Explicit unknowns become design-phase questions; hidden unknowns become production bugs.

**Pass condition:** At least 2-3 unknowns are stated as "the design phase will resolve X by Y date/milestone." If the answer is "no unknowns," the PRD is lying or the feature is trivial.

**Adversarial counter-pass:** Name an assumption the PRD makes that isn't called out. Examples: an implicit data shape, a UX convention inherited from a sibling product without being verified for this one, a customer's tolerance for friction, a regulatory regime, a deployment topology. Every "obviously" you can identify is an unknown the PRD didn't name.

### Pass 5 — Success metric

**Check:** How will we know AFTER launch whether this worked?

- **Leading indicator** — measurable within 1-2 weeks of launch (usage, conversion, error rate, time-to-value)
- **Lagging indicator** — measurable at 1-3 months (retention, revenue, satisfaction, churn delta)

**Why:** Without a success metric, "ship" becomes the goal instead of "ship something that worked." Post-launch you can't tell whether to invest more or pivot. PRDs without success metrics are political documents, not engineering ones.

**Pass condition:** Both leading and lagging indicators are named with target values (or target movement direction + magnitude).

**Adversarial counter-pass:** Name a way the metric could move in the right direction without the feature actually working (Goodhart's law). Examples: usage goes up because the feature is unavoidable, not because users love it; retention goes up because we removed an off-ramp, not because we added value; satisfaction goes up because the comparison cohort is smaller. If you can name such a path, the metric is gameable and needs a paired anti-metric.

### Pass 6 — Sequencing / dependency

**Check:** What does this feature depend on? What depends on this feature shipping? Is the ordering explicit?

**Why:** Features ship in dependency order. A PRD that doesn't acknowledge dependencies will produce a design that assumes everything is parallel — and then blow up at integration time. PRDs that ignore downstream dependents leave consumers in the dark and force last-minute rework.

**Pass condition:** Upstream dependencies are named with status (shipped / in-flight / not started); downstream features are named with the contract this PRD owes them.

**Adversarial counter-pass:** Name a dependency the PRD assumes is solved but isn't (e.g., "users will already have X" when X is itself a future feature). Also: name a downstream feature that quietly depends on a particular shape this PRD produces — and isn't acknowledged.

### Pass 7 — Spec freeze readiness

**Check:** Passes 1-6 are all cleared. Adversarial counter-passes addressed. Overlap and OSS scans complete (see below). Stakeholders have signed off (or, for solo work, you have signed off in a separate cognitive role from the author role).

**Why freeze matters:** From this moment on, scope changes require a documented PRD amendment (a delta commit to the PRD). Without an explicit freeze, scope creep during design / impl-plan / implementation phases compounds — the team builds against a moving target. Freeze gives the downstream phases something stable to react to.

**What "frozen" means in practice:**

- No more "obvious requirements" added to the PRD without an amendment commit
- `apex:design-feature` can now load and trust the spec
- `apex:impl-plan-review` can scope the layered PR stack against a fixed acceptance surface
- Integration tests will be planned 1:1 against Pass 2's scenarios (`apex:python-review/rules/testing.md` → "PRD ↔ Integration Test Mirror")
- If reality later forces a spec change, it's an EXPLICIT amendment, not a silent re-interpretation during implementation

**Pass condition:** A frozen-spec marker exists. Format doesn't matter (commit message, git tag, YAML field, status-doc row, doc heading) — the marker is what matters. The PRD itself states "frozen as of <date / commit / amendment-N>."

**Adversarial counter-pass:** Name a part of the spec that's still ambiguous enough that two implementers would build subtly different things. If found, the spec isn't ready to freeze — that ambiguity needs resolving first. Also: name an "obviously" implied behavior that isn't actually written down — those are the silent re-interpretations that bite during implementation.

## Existing-product overlap scan

Before claiming the PRD is sound, scan the rest of the product for overlap. **Most "new features" are partial duplications of existing features**, especially in mature codebases where features accreted over time.

**How:**

1. **Grep the codebase** for the proposed feature's key nouns and verbs:
   - Service / handler / endpoint names that imply the same intent
   - UI strings / labels that target the same user goal
   - Database tables / models / event types in the domain
2. **Read the relevant module's `README.md`, design doc, or status row** to see what's already shipped.
3. **Ask** — does this PRD add a third thing alongside two that exist? Does it create a parallel path for something already covered? See `apex:apex-flow` §1a Q2 (codebase reconnaissance) and `rules/principles.md` §3 (pure-addition designs are a smell).

**Pass condition:** Either no overlap exists (proven by the grep, not waved off), OR the PRD explicitly states "we're replacing / extending / refactoring existing feature X because [reason]."

**Adversarial counter-pass:** Show the 2-3 closest existing features. For each, explain why it's NOT what we want. If the answer is hand-wavy ("it's different"), the overlap is real and unaddressed.

## OSS-alternatives scan

For any non-trivial feature, ask: **does open-source already solve this?** Reinventing without checking is a slow, expensive form of NIH ("not invented here").

**How:**

1. **Search** for libraries that implement the core capability:
   - Language-specific package manager (PyPI, npm, crates.io, go.dev)
   - GitHub search by topic / star count / recency
   - "Awesome-X" lists for the domain
2. **Identify reference implementations** — well-known OSS products that solved the same problem (Sentry for error tracking, Mailgun for email, ImageMagick for image manipulation, Prefect/Airflow/Temporal for workflows, etc.). Even if you don't adopt them, their design choices are free education.
3. **Decide** for each candidate:
   - **Use directly** — adopt the library; build only the integration
   - **Use as reference** — read the design but build our own (e.g., license incompatible, domain-specific tweaks needed, vendor risk)
   - **Avoid** — explicitly state why (abandoned, security issue, doesn't fit our deployment model)

**Pass condition:** The PRD names ≥1 OSS alternative considered, with the use / reference / avoid decision and rationale. Bonus: name 1-2 reference implementations even if not adopting.

**Adversarial counter-pass:** Find an OSS library the PRD missed. If one exists with significant overlap and the PRD doesn't address it, the OSS scan was incomplete. Common misses: telemetry, queueing, retries, rate limiting, feature flags, A/B testing, payment processing, search, auth.

## Adversarial pair pattern (heavier — for non-trivial PRDs)

The inline adversarial counter-passes above are the *cheap* version (one agent does both). For non-trivial PRDs, dispatch the review as **two parallel agents** via `apex:adversarial-pair` (apex's canonical dispatch mechanic):

- **Cooperative agent** — runs the 7 passes + overlap scan + OSS scan in "steelman" mode. Finds what works, what's well-stated, what's defensible. Reports with citations.
- **Adversarial agent** — runs the same checklist in attack mode. Each adversarial counter-pass becomes the primary lens. Finds what's vague, what's assumed away, what's overstated, what's missing. Reports with file:line citations from the PRD itself.

Both agents run in isolated worktrees with the same input PRD. They report independently. Reconcile their findings. Most real PRD weaknesses surface only when both views are produced and compared — single-pass review reliably misses the adversarial half.

## Pass/fail summary

The PRD passes if:

- All 7 passes meet their pass conditions
- Existing-product overlap is explicitly addressed (no overlap proven, or replacement/extension stated)
- ≥1 OSS alternative was considered with rationale
- The adversarial counter-pass (or adversarial agent) produced findings that have either been addressed in the PRD or explicitly accepted with reason

Fail any → the PRD is not ready for `apex:design-feature`. Send it back for revision; don't paper over with optimistic design work. A weak PRD compounds into a weak design which compounds into expensive rework.
