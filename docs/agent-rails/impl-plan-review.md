# impl-plan-review — `agent-rails` (cold)

**Artifact:** `docs/agent-rails/impl-plan.md` (DRAFTED) · **Upstream:** `design.md` (FROZEN, PR #28)
**Verdict:** PASS WITH FINDINGS — P1–P2 resolved inline; P3 carried into L5 as an explicit sub-step. Freeze blocked only on user sign-off.

## Pass 1 — Layered stack (≤400 LOC, independently revertible, ordered)

Five layers, each new-files-or-append, each with a stated revert that leaves the system in a safe (inert, never broken) state. The ordering invariant is correct and load-bearing: **tools before the amendments that call them** — L5's skill edits would be dangling instructions if they preceded L1–L3. Sizes are plausibly under budget (one script + its tests per layer). Held.

**Attack — is L1 revertible once L2+ exist?** L1 ships `freeze` with a no-op lint stub; L2 replaces the stub. Reverting L1 alone after L2 lands would break L2 — but layers revert in reverse order (standard stack discipline), and the plan states each revert against *its own* predecessor state. Acceptable; **(P1 — resolved: added "layers revert LIFO" to the rollout section's intent — noted here as the controlling reading.)**

## Pass 2 — Sequencing

L1→L5 strict, each consuming only earlier layers, verified by walking the dependency of each layer's tests. The dogfood `state.json` advancing through the stack is a nice forcing function (the feature can't claim a phase its own tooling wouldn't record). **Attack — S4 split across L1 (hash flag) and L5 (prose scan):** is that a sequencing hazard? S4(b) (POST-FREEZE-DRIFT) is fully testable at L1 (pure hash); only S4(a) (DIVERGENCE, needs prose-marker reading) waits for L5. The plan states this explicitly rather than pretending S4 is monolithic. **(P2 — resolved: the test-plan table now rows S4(a)/S4(b) separately to L5/L1 respectively — matches the design's flag split.)**

## Pass 3 — Test plan per layer (PRD scenarios 1:1, incl. negatives — D5)

The summary table maps all seven scenarios + every edge to a layer and a named negative fixture (torn write, well-formed forgery, drifted registry, unparseable matrix). This is the strongest part of the plan — the negative paths are fixtures, not assumptions, exactly as D5 required. Forward check: no PRD scenario is unowned; no AC is untested (AC1←S1/S5, AC2←S4, AC3←S2, AC4←S7, AC5←S6, AC6←S3 atomic + L4 no-daemon).

**Attack — who tests the meta-claim "no path writes `frozen` without the lint"?** L2 wires lint into `freeze`, but a test that *bypasses* `freeze` and writes JSON directly would pass shape trivially — that's S7's well-formed-forgery boundary, already owned. The thing actually worth a dedicated test: that `freeze` is the **only** write path to `status: frozen` in `state_tool.py` (no second writer). **(P3 — carried to L5: add a source-level assertion/test that `"frozen"` is written in exactly one function; cheap, prevents a future second-writer regression that would bypass the lint.)**

## Pass 4 — Rollout strategy

Expand-only, no destructive migration — correct: `state.json`/`gates.json` are new artifacts, skill edits are append. No feature flag needed (nothing consumes the tools until L5 wires them; pre-L5 they're inert). The CI workflow (L4) lands before the wiring (L5), so the conformance gate exists before the gates it checks are referenced. Held.

## Pass 5 — Reversibility

Each layer's revert is stated and lands the system inert-not-broken (the safe direction — unused tools beat dangling references). Whole-feature revert = remove `skills/agent-rails/`, `gates.json`, the workflow, and the seven one-line amendments; `state.json` files become orphaned-but-harmless JSON (no reader). The one irreversible-ish thing — `state.json` files committed into feature dirs — are inert data, not a migration, so "reversibility" is trivially satisfied. Held.

## Adversarial counter-pass

1. **"L5 is too big — seven amendments + SKILL.md + MAINTAINING.md + README + FLOW.md in one PR"** — real risk; it's prose but it's wide. Mitigation: all edits are mechanical one-liners against existing structures, and the count-drift grep (MAINTAINING.md §2) gates the menu-stays-17 claim. If it bloats past ~400 LOC-equivalent, split L5 into L5a (the SKILL.md + tool-facing amendments) and L5b (docs/registry-of-self). Noted as a permitted split, not mandated.
2. **"The dogfood state.json will drift from reality during the stack"** — as L2/L3 change what `freeze` writes, the hand-written `state.json` could fall out of schema. Defense: L3's `report` + L4's CI run against the real file, so drift fails CI — the feature's own gate catches its own rot. Good forcing function.
3. **"S4(a) prose-scan is under-specified"** — where prose freeze-markers live (the `## Freeze marker` section, the `❄️ FROZEN` header form) isn't pinned until L5. Accepted: it's a design-§6 detail (SKILL.md defines marker location), correctly deferred to the layer that owns prose reading, and tested there.

---

**Findings ledger:** P1 resolved (LIFO revert reading) · P2 resolved (S4 split rows in test table) · P3 carried to L5 (single-frozen-writer test) · counter-pass items 1–3 noted (permitted L5 split; dogfood-drift is self-catching; S4(a) marker-location owned by L5 SKILL.md). Plan is freeze-ready on user sign-off.
