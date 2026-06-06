# design-review — Execution-tier handoff + optional bead lineage

Applied `apex:design-review` (5+1 passes, adversarial lens, cold pass) to `design.md`, plus the freeze ceremony. **[FIXED]** = folded into the design before freeze; **[ACCEPTED]** = explicit residual.

## Adversarial passes

**Pass 1 — Scenarios.** Walked D1–D5.
- *Missing flow:* **re-handoff after a partial Gastown run** (some beads merged, some failed, the plan was then amended) was not a listed flow. **[FIXED]** — surfaced in design Pass 1 and handled by **idempotent emit keyed on `bd` hash-IDs** (re-emit only changed/failed beads; merged beads are immutable history).
- *Scenario the design can't handle without rework:* none found — the staging-JSONL + atomic `bd import` already covers partial-state cleanly.

**Pass 2 — MVP cut.** Struck each element:
- Strike the **bead emitter** → AC2/AC4 fail. Strike the **gate wiring** → AC3 fails (and re-creates the exact Refinery-bypass the feature exists to kill). Strike **tier-selection** → AC1/AC5 fail. Irreducible — no strikeable core element.
- *Added-beyond-PRD element:* **threshold configurability.** The PRD (U4) required only a *default*; "configurable" was scope I added. **[FIXED]** — struck from MVP to a hardcoded constant; configurability moved to the deferral list.

**Pass 3 — Deferral list.** Checked each for hot-fix-bite:
- 1:1→1:many, generic SPI, spec-view rendering, bidirectional sync, configurable threshold — none bite within 24h (1:1 is always correct; the others are absent-but-not-broken). **[PASS]**
- *Confirmed the gate wiring is correctly NOT deferred* — deferring it is the one move that would embarrass within a single run.

**Pass 4 — Integration.**
- *Duplication risk:* the bead store becoming a **second source of truth** competing with the canonical markdown. **[FIXED]** — added an explicit **ownership split** to the design: *scope/lineage* is apex-owned (projected from frozen docs, docs win on drift); *execution status* is Gastown-owned (one-way read-back). Status and scope don't cross, so no competing truth.
- *Broken invariant:* none — the fail-closed Witness wiring preserves "review gates are mandatory."

**Pass 5 — Failure modes.**
- *Unspecified user-visible behavior:* the **Witness-absent fallback** ("gate the MRs pre-merge") is named but the *who-triggers/what-blocks* detail is thin. **[ACCEPTED]** as an impl-plan-level detail (the behavior — block human merge until apex gate passes — is stated; the mechanism is an implementation choice), flagged for `impl-plan`.
- *Feature-unique mode:* **`gt`/`bd` version skew** — covered via `bd`'s schema contract + `bd ping` precheck. No gap.

**Pass 6 — Attack surface.** STRIDE-lite present; the load-bearing control (fail-closed gate) and the injection mitigation (`bd import` of data, never shell interpolation) are explicit. Heavier two-agent threat-model omission is justified in the doc (no auth/payment/multi-tenant/crypto surface). **[PASS]**

## Overlap + OSS (audit, not re-run)
Both ran in design-feature and are non-perfunctory. Adversarial spot-check: no synonym-grade internal miss (`dispatching-parallel-agents` is wrapped, not duplicated); no >1k-star OSS miss (retries/queueing/recovery/merge-queue are all provided by Gastown/beads, correctly "adopt not build").

## Adversarial-pair omission
The heavier two-agent pair was **not** dispatched. **Justified:** no attack surface in the auth/payment/multi-tenant/crypto set; this is a design-doc artifact, not shippable code; the single real control is simple and fail-closed. Per the skill, the omission is stated, not silent.

## Freeze verdict

**FROZEN (2026-06-06).** Two minor findings (MVP-configurability strike, source-of-truth ownership split) were applied — both minor revisions, not a reshape (< the ≥3-finding reshape threshold). All adversarial findings are resolved or explicitly accepted. The four PRD unknowns are resolved in the design (U1/U3 by the spike; U2/U4 by design decision).

**Next:** `impl-plan` → `impl-plan-review`. Run `api-surface-review` on the bead-emit format before it locks. The residual real-world risk is integration drift against live `gt`/`bd`/Refinery versions — a `bd ping` / schema-contract precheck is the mitigation, but the first build should be validated against an actual Gastown install (a spike task in the impl-plan).
