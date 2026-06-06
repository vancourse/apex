# Design — Execution-tier handoff + optional bead lineage

**Status:** FROZEN as of 2026-06-06 (post `design-review`) · **Slug:** `execution-tiers`
**PRD:** `prd.md` (FROZEN 2026-06-06) · **Design-feature pass.** Adversarial re-pass in `design-review.md`.

> **Spike result (resolves PRD U1/U3).** Grounded against the real projects:
> - **beads (`bd`)** is a graph issue tracker for agents — epics/tasks, **four dependency-link kinds**, parent/child pointers, JSONL export, `bd ready --json`. → apex lineage maps natively; **U1 largely resolved**.
> - **Gastown's Refinery** runs **verification gates** and a **Witness agent that reviews every change** before a Bors-style merge. → apex gates plug into that existing slot; we do **not** invent a parallel gate. **U3 resolved** (with the post-MR fallback demoted to a version-skew contingency).

---

## Pass 1 — User-flow scenarios (the operator's flows)

The "user" here is the engineer (or driving agent) past the design-freeze, holding a frozen `impl-plan.md`.

- **D1 — Tier-1 handoff (large, Gastown present).** Operator runs the handoff on a 6-layer frozen plan with `gt`+`bd` available → apex prints the tier decision (`Tier 1: gt/bd present, 6 parallelizable layers ≥ threshold 3`), stages a bead graph, runs the coverage audit, `bd import`s on pass, hands to Gastown. *Edge:* two independent layers → their task beads share no blocking link.
- **D2 — Size gate (small, Gastown present).** 1-layer plan, Gastown available → `Tier 2: 1 layer < threshold 3` — apex does **not** spin up the fleet. *Edge:* exactly 3 layers → Tier 1 (threshold is inclusive `≥`).
- **D3 — Degrade (neither executor).** 4-layer plan, no `gt`, no superpowers → `Tier 3: baseline sequential` printed, proceeds without error. *Edge:* superpowers present, Gastown absent → Tier 2.
- **D4 — Coverage audit fails closed.** Emitter drops a layer (or a layer has no test plan) → audit names the orphaned layer and **blocks `bd import`** — nothing partial enters the bead store. *Edge:* a task bead with no parent-epic (scenario) lineage is flagged "execution work with no spec ancestor."
- **D5 — Gate inside the Witness slot.** Tier 1; a bead's output fails apex `security-review` (run as the Witness check) → the Refinery does **not** merge that bead; sibling independent beads proceed; a dependent bead waits. *Edge:* the Witness slot is unavailable in the installed Gastown version → fall back to gating the resulting MRs *before human merge* (U3 contingency).

*Adversarial (answered in `design-review.md`):* a flow the list misses — **re-handoff after a partial Gastown run** (some beads merged, some failed, plan amended). Surfaced there; handled by idempotent emit keyed on `bd` hash-IDs.

## Pass 2 — MVP cut

The smallest thing that delivers the PRD's AC1–AC5:

1. **Tier-selection emitter** — reads the frozen `impl-plan.md`, probes `gt`/`bd` and superpowers (reusing `/apex:setup`'s detection), counts parallelizable layers, prints the tier + the two-signal rationale (AC1, AC5).
2. **Tier-1 bead emitter** — translates the layered stack into a `bd` JSONL: PRD scenario → **epic/parent bead**; impl-plan layer → **task bead** (child of the scenario epic it serves = lineage link); layer sequencing → **blocking dependency link**; the layer's per-layer test plan → the bead's body/done-criteria (AC2).
3. **Bead-coverage audit** — a graph query over the staged JSONL: every layer has ≥1 task bead; every task bead traces to ≥1 scenario epic; no orphans. Fails closed, blocks `bd import` (AC4).
4. **Gate wiring (doc/config)** — register apex `security-review` + `verification-before-completion` as the Gastown **Witness / verification gate**, fail-closed (AC3).

That's MVP. Each piece is independently testable; together they satisfy all five ACs.

## Pass 3 — Deferral list

- **1:many layer→bead auto-decomposition** (V2) — MVP emits **1 task bead per layer**; splitting a layer into parallel sub-beads is manual for now. *Trigger:* a real plan where a single ≤400-LOC layer has genuinely independent parallel files. *Not a hot-fix risk:* 1:1 is always correct, just less parallel.
- **Generic executor SPI / plugin-adapter** (V2+) — only three concrete tiers exist; abstract when a fourth appears. *Trigger:* a 4th executor.
- **Bead-graph rendering in `spec-view`** (V2) — visualize the lineage graph. *Trigger:* operators asking to *see* coverage, not just pass/fail.
- **Bidirectional sync** (deferred, maybe never) — reading bead *status* back into apex artifacts. *Trigger:* explicit demand; high ambient-cost risk, guard hard.
- **Configurable size threshold** (V2 nicety) — MVP hardcodes `≥3 parallelizable layers`; per-project configuration deferred (`design-review` strike — PRD required only a default). *Trigger:* a project whose parallelism economics differ from the default.

*Adversarial check (per skill): does any deferral hot-fix-bite?* The gate wiring (#4) is **not** deferred precisely because deferring it = unreviewed merges within 1 run = exactly the embarrassment the PRD exists to prevent. Confirmed in `design-review.md`.

## Pass 4 — Integration with existing surface

Reuses, does not duplicate:

- **`/apex:setup` capability probe** — extended for `gt`/`bd`, not re-implemented (≥2-primitive reuse #1).
- **`impl-plan-review` output** — the frozen layered stack is the emitter's *sole input*; we consume its existing structure (layers, sequencing, per-layer test plan) rather than re-deriving (reuse #2).
- **`security-review` / `verification-before-completion`** — run *as-is* in the Witness slot; the tier layer invokes them, doesn't reimplement review.
- **beads / Gastown** — consumed via their CLIs (`bd import`, `bd ready`, `gt`); apex bundles neither.

**Invariants preserved:** (a) *frozen-artifact-as-contract* — the emitter reads only frozen inputs; (b) *structural-ephemeral / semantic-durable* — the bead graph is a **projection** of the canonical markdown, regenerable, never the source of truth (same rule apex applies to code graphs). **Invariant deliberately *not* broken:** review gates remain mandatory — the tier layer cannot route *around* them (the Witness wiring is fail-closed).

**Ownership split (refined in `design-review`):** a bead carries two kinds of data with *different owners*. **Scope/lineage** (which scenario, which layer, done-criteria) is **apex-owned** — projected from the frozen docs, re-emitted if it drifts, docs win. **Execution status** (open / in-progress / blocked / done) is **Gastown-owned** — it is the legitimate execution truth and flows *one way* back (apex reads it, never lets it overwrite scope). This prevents the "bead store becomes a second source of truth" failure: status is Gastown's, scope is apex's, and they don't cross.

*Adversarial (Pass 4):* the one duplication risk — does the bead store become a *second* source of truth competing with the markdown? Mitigated by the projection invariant: beads are emitted *from* frozen docs and never edited as the primary; if they drift, the docs win and beads are re-emitted.

## Pass 5 — Failure modes (user-visible behavior stated)

- **`gt` present, `bd` store not initialized** → detect via `bd ping`; user sees `bead store not initialized — run 'bd init' or proceed Tier 2`; does not crash.
- **Partial emit mid-translation** → emit to a **staging JSONL**, audit, and only `bd import` atomically on pass. A failure before import leaves the bead store untouched — never a half-imported graph.
- **`gt`/`bd` version skew** → `bd` ships a JSON schema contract + `bd ping`; apex checks schema compatibility before emit; on mismatch: `bead schema vX unsupported — update bd or proceed Tier 2`.
- **Witness slot absent (older Gastown)** → fall back to gating the resulting MRs *before human merge* (U3 contingency); user sees `Witness gate unavailable — apex will gate MRs pre-merge instead`.
- **Concurrent handoffs to one bead store** → `bd` hash-IDs prevent collisions by design; apex additionally namespaces beads by feature slug. User-visible: independent features don't clobber each other.
- **Coplan exhausted / fleet over-spawns on a huge plan** → bounded by the size threshold + a max-layer cap; above the cap apex refuses Tier 1 with `plan too large for a single convoy — split the impl-plan`.

## Pass 6 — Attack surface (STRIDE-lite)

This feature **has** modest attack surface (it shells out to `gt`/`bd` and gates merges), so not "no attack surface":

- **Tampering / Elevation of privilege** — the gate-before-merge **is a security control**; bypassing it merges unreviewed code. *Mitigation:* apex gates run as a **fail-closed required** Witness/verification check — if the gate can't execute, the bead does **not** merge.
- **Injection** — impl-plan / PRD text flowing into `bd create` shell args = command-injection risk. *Mitigation:* emit via `bd import` of a **data JSONL file**, never string-interpolate plan prose into a shell command line.
- **Information disclosure** — scenario/PRD text lands in the bead store (JSONL in git). Already in-repo, so acceptable; *note:* don't push a private bead store to a shared remote if scenarios carry sensitive data.
- **DoS** — a pathological plan spawning a huge fleet. *Mitigation:* size threshold + max-layer cap (Pass 5).
- **Spoofing / Repudiation** — inherited from Gastown's own agent-identity model; out of apex's scope (accepted residual, documented).

Heavier two-agent threat-model **not** dispatched — justified: no auth/payment/multi-tenant/crypto surface; the one real control (fail-closed gate) is simple and explicit. (Per `design-review` rules, this omission is stated, not silent.)

## Overlap scan
No internal duplication (see Pass 4 — `/apex:setup`, `impl-plan-review`, `security-review` all reused). Closest synonym check: "orchestration" / "dispatch" → superpowers' `dispatching-parallel-agents` is the Tier-2 executor, explicitly *wrapped*, not duplicated.

## OSS scan
- **beads (`bd`)** — **adopt** as the lineage substrate (epics/tasks/4-dep-links fit exactly). ([repo](https://github.com/steveyegge/beads))
- **Gastown** — **adopt** as Tier-1 executor; reuse its Witness/Refinery gate slot. ([repo](https://github.com/steveyegge/gastown))
- **Temporal / Airflow / Prefect** — **reference** for dependency-graph + recovery semantics; not adopted (heavyweight, non-Claude-native).
- **Bors / merge-queue tooling** — **reference**; Gastown's Refinery already *is* a Bors-style queue, so nothing to add.
- *Adversarial miss check:* the usual misses (retries, queueing, recovery, merge-queue) are all **provided by Gastown/beads**, reinforcing integrate-don't-reinvent.

## Design-decision resolutions of PRD unknowns
- **U1 — RESOLVED:** beads carry lineage via epic→task parent/child + dependency links; acceptance criteria live in the bead body/done-criteria (custom field if available, else body). No sidecar needed for MVP.
- **U2 — RESOLVED (MVP):** emitter is **1:1 layer→bead** for MVP; 1:many auto-split deferred (Pass 3). Coverage audit checks "every layer ≥1 bead, every bead → scenario, no orphans" so it already tolerates a future 1:many.
- **U3 — RESOLVED:** gate via Gastown's existing **Witness/verification slot**, fail-closed; post-MR gating is the version-skew fallback only.
- **U4 — RESOLVED:** default threshold = **≥3 parallelizable layers** for Tier 1; tie at 3 → Tier 1 (inclusive). **MVP uses a constant** (`design-review` struck "configurable" from MVP — the PRD only required a default; configurability is a V2 nicety, now in the deferral list). Documented so two implementers route identically.

## Hand-off
Once `design-review` freezes this: `impl-plan` (layered build plan for the emitter + audit + gate wiring) → `impl-plan-review`. The bead emitter is an internal CLI/format surface → run `api-surface-review` on the emit format before locking it.
