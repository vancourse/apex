# prd-review — Cross-artifact consistency analysis

Applied `apex:prd-review` (7 passes + adversarial counter-pass each + overlap + OSS scans), cold, against `prd.md`. **[FIXED]** = folded into the PRD before this record; **[ACCEPTED]** = recorded as unknown/out-of-scope with reason.

**Pass 1 — Acceptance criteria observable.** PASS. AC1–AC5 each name an observable output (a flag, a citation, a refusal).
- *Adversarial:* AC1 ("every scenario maps to a design element") could be satisfied by a coarse mapping that's technically present but meaningless. **[FIXED]** — added the §6 anti-metric requiring **per-scenario granularity** rows, so a coarse all-in-one map is itself a visible smell.

**Pass 2 — Scenarios enumerated + tagged.** PASS (5 scenarios, edge cases, all integration-tagged with an explicit "no E2E, justified" note; S1 decomposed into use-cases S1.1/S1.2 — dogfooding the new decomposition feature).
- *Adversarial — happy path without failure companion:* the first draft had S1 (clean) + S2 (drop). **[FIXED]** — added **S3** (orphan), **S4** (contradiction), **S5** (un-frozen upstream): every AC now has a paired failure scenario.

**Pass 3 — Out-of-scope.** PASS (5 items w/ rationale).
- *Adversarial — obviously in-scope but missing:* the first draft didn't say whether it does free-text semantic matching. That ambiguity would balloon scope into an NLP-equivalence engine. **[FIXED]** — explicitly scoped OUT "semantic NLP equivalence beyond cited structural mapping"; the analyzer maps IDs, deterministically.

**Pass 4 — Unknowns named.** PASS.
- *Adversarial — hidden assumption:* the draft assumed scenarios/elements/layers already cross-reference cleanly. They partly do (post-0.3.2 lineage) but not fully. **[FIXED]** — **U1** (mapping anchor: reuse existing IDs vs. explicit markers) + **U3** (1:many cardinality, same problem as the bead audit) named as design unknowns.

**Pass 5 — Success metric.** PASS — leading + lagging + anti-metric (Goodhart guard on coarse mapping) all present.

**Pass 6 — Sequencing.** PASS, and notably strong: the feature is **only buildable because 0.3.2 shipped the scenario IDs + layer→scenario lineage** — a clean upstream dependency, explicitly named with status.
- *Adversarial — dependency assumed solved:* is the lineage metadata *actually* present in real artifacts, or aspirational? **[ACCEPTED]** — flagged in U1: design must confirm the anchor exists in practice before committing to "reuse IDs" vs. "require markers."

**Pass 7 — Freeze readiness.**
- *Adversarial — two implementers diverge:* "when does it fire / USER vs AUTO" was unspecified → two builders would wire it differently. **[FIXED]** — captured as **U2** with a leaning (AUTO at impl-plan-freeze + USER on-demand) for the design to settle.

**Overlap scan.** PASS. The one real adjacency — `test-coverage-audit` Pass 1 (spec↔test mirror) — is addressed by **reuse**: the analyzer extends that scenario-enumeration one hop upstream (spec↔design↔plan) rather than re-implementing it. Adversarial spot-check: no synonym-grade duplicate skill exists.

**OSS scan.** PASS. Spec Kit `/analyze` = reference (direct inspiration, not adoptable); classic RTM/DOORS = reject (enterprise weight); OpenAPI diff = `api-surface-review`'s slice. No missed widely-adopted lightweight prior art.

## Verdict

**PASS — freeze-candidate.** All 7 passes meet conditions; every adversarial finding resolved in the PRD or recorded as U1–U3. The review materially changed the PRD (3 new failure scenarios, the semantic-scope cut, the anti-metric, 3 unknowns) — not a rubber stamp.

**Residual risk:** **U1** (does the lineage anchor exist cleanly enough to map deterministically, or does the analyzer need to *require* explicit markers — which would push authoring cost upstream?). That's the load-bearing design-phase question.
