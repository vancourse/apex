# design-review — Cross-artifact consistency analysis

Applied `apex:design-review` (5+1 passes, adversarial lens, cold) to `design.md`, plus the freeze ceremony. **[FIXED]** folded in before freeze; **[ACCEPTED]** = explicit residual.

**Pass 1 — Scenarios.** Walked S1–S5.
- *Missing flow:* a scenario realized by a **design failure-mode or threat-model entry**, not a numbered scenario, would falsely flag the layer as ORPHAN. **[FIXED]** — design now treats failure-modes + threat-model entries as valid ancestors, not just `S#` scenarios.

**Pass 2 — MVP cut.** Struck each element:
- Strike the loader/freeze-check → AC5 fails. Strike node-extraction → no matrix. Strike the three checks → AC1–AC3 fail. Irreducible.
- *Added-beyond-PRD:* the first design draft implied *full* CONFLICT detection in MVP. **[FIXED]** — MVP CONFLICT is scoped to the **deterministic out-of-scope-violation case** only; free-text conflict deferred (avoids the hallucination surface the PRD scoped out). This is the key MVP cut.

**Pass 3 — Deferral list.** Free-text conflict, spec-view render, cross-feature, auto-fix — none hot-fix-bite (MVP is correct, narrower). *Confirmed* the read-only invariant is correctly **not** deferred (auto-fix stays out — deferring read-only-ness would break the author/review separation).

**Pass 4 — Integration.**
- *Duplication risk:* re-implementing scenario parsing that `test-coverage-audit` Pass 1 already does. **[FIXED]** — design explicitly *reuses* that enumeration and extends it one hop; doesn't fork it.
- *Broken invariant:* none — read-only + ephemeral preserved; runs in addition to vertical reviews.
- *Adversarial — the anchor pushes cost upstream?* The `realizes S#` design tag could become authoring burden. **[ACCEPTED, mitigated]** — it's **optional**; untagged elements self-flag as ORPHAN rather than erroring, so the cost is opt-in and the signal is still produced. This is the cleanest resolution of PRD U1's load-bearing risk.

**Pass 5 — Failure modes.** Each has stated user-visible behavior (absent → status; un-frozen → freeze-first; no IDs → re-run Pass 2; bad lineage → CONFLICT; huge → paginate).
- *Feature-unique mode:* **pre-0.3.2 PRD with no scenario IDs** — covered (degrade with a re-run-Pass-2 message), not a crash.

**Pass 6 — Attack surface.** STRIDE-lite present; the one real risk (**path traversal via feature slug**) has a stated mitigation (resolve within `docs/<slug>/`, reject path separators). No external input/PII/auth. Heavier two-agent threat-model omission justified (read-only local-markdown tool).

**Overlap + OSS.** Audited, not re-run. No synonym-grade internal miss; Spec Kit `/analyze` correctly referenced, not adoptable. **[PASS]**

**Adversarial-pair omission.** Single-agent review — justified: no auth/payment/multi-tenant/crypto surface; design-doc artifact, not shippable code; the one control (path-scope) is simple.

## Freeze verdict

**FROZEN (2026-06-06).** One real MVP cut (scope CONFLICT-MVP to the deterministic case) and one Pass-1 fix (non-scenario ancestors) applied — minor, not a reshape. All adversarial findings resolved or accepted. PRD U1–U3 resolved in the design.

**Next:** `impl-plan` → `impl-plan-review`. Residual real-world risk: whether the `serves S#` lineage is consistently present in real impl-plans (if authors skip it, the analyzer's backward-trace is weak) — the first build should validate against an actual frozen feature folder (e.g. `docs/execution-tiers/`).
