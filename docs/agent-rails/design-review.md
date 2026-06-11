# design-review — `agent-rails` (cold adversarial re-pass)

**Artifact:** `docs/agent-rails/design.md` (DRAFTED) · **Upstream:** `prd.md` (FROZEN, PR #27)
**Verdict:** PASS WITH FINDINGS — D1–D3 resolved in the design (noted inline below); D4 accepted risk; D5 carried to impl-plan. Freeze blocked only on user sign-off.

---

## Pass 1 — Scenario realization (attack: does every frozen scenario have an owner?)

S1→§6, S2→§4, S3→§2 (atomic writes), S4→§2 (computed flags), S5→§5 (`requires_frozen` join), S6→§5 (`registry_check.py`), S7→§2 (evidence-fields-mandatory rule). Forward coverage complete; no orphan design element — every §1 table row traces to a scenario. **Attack on S4(b):** the byte-hash decision means *any* reformat invalidates a freeze. The design states this is deliberate and names the resolution path (amendment re-freeze) — held, but the SKILL.md must say it loudly or the first formatter incident becomes a lint-loosening PR. **(D1 — resolved: §2 now carries the "stated here so nobody fixes it later" line.)**

## Pass 2 — MVP cut (attack: is anything here speculative?)

The cut is tight: no DSL for `fires` (explicitly rejected), no cross-feature index, no generation direction, no hook consumption. **Attack:** is `adr` in the lint's type table speculative? No — `adr-review` is one of the six amendment sites (§7); shipping the lint without the type would orphan that amendment. Held. **Attack:** six skill amendments in one stack — scope creep? They are one-line additions to existing freeze ceremonies, and F5 (carried from prd-review) makes them load-bearing, not optional. Held.

## Pass 3 — Deferral list (attack: is anything deferred that the MVP secretly needs?)

Hook-side registry reads deferred (U5): does the MVP then fail its own purpose — the agent must *choose* to consult state? Partially — but the SKILL.md's STOP instruction + the freeze tools' internal lint + CI conformance give three enforcement layers that don't depend on per-edit hooks, and the PRD's lagging metric (zero advanced-past-unfrozen) will expose whether the deferral was wrong. Genuine risk, measured, with a revisit trigger named. **(D4 — accepted risk: agent-discipline-dependent resume, mitigated by the STOP rule + metric; revisit if dogfooding shows misses.)**

## Pass 4 — Integration (attack: does this fight any existing surface?)

- `cross-artifact-consistency`: reuses its regexes (stated), extends its taxonomy with three flags + UNMANAGED (stated in §9) — **(D2 — resolved: the UNMANAGED check was originally implied; §9 now names it as an explicit one-check amendment to that skill, which therefore joins the §7 amendment list as a seventh site.)**
- `detect-stack`: file-discipline reuse only; no contact.
- `execution-tiers` boundary: gate state ≠ execution status — preserved; the registry carries no executor fields.
- FLOW.md: stays canonical for humans; the matrix-check is read-only. The "when to skip phases" routing (§9, fix-shaped work) correctly keeps exemption logic in prose rather than JSON — a registry that encoded skip rules would fork FLOW.md's authority. Held.

## Pass 5 — Failure modes (attack: walk each one as the operator)

Torn write / unparseable JSON / parser failure all fail closed — verified against the stated mechanisms. **Attack:** `state_tool.py freeze` is a single entry point that runs the lint internally — what if someone writes `frozen` via a text editor with all evidence fields well-formed and the hash freshly computed? That is the S7 edge (well-formed forgery), accepted at the PRD level with the out-of-repo verification boundary (§3). Consistent, not a new hole. **Attack:** two features freezing concurrently? Different `state.json` files per feature dir — no shared write target; the atomic-replace covers same-file races. Held.

## Pass 6 — Attack surface re-walk

No external input, no network, no privilege escalation, no secrets in state — the threat-model-lite scope (§10) is proportionate, and both real threats carry stated boundaries rather than pretended mitigations. The honest-rail posture survives the re-walk.

## Adversarial counter-pass (attack the design's own seams)

1. **"The registry will be wrong about reality"** — `gates.json` is authored; authored docs drift. Defense: drift against FLOW.md is CI-checked (S6); drift against *actual skill behavior* is not. Residual: a skill could change its firing condition in SKILL.md prose without touching either file. **(D3 — resolved: §7's amendment recipe now applies in reverse — MAINTAINING.md gains one line: "adding/changing a gate's phase or freeze role touches gates.json + FLOW.md matrix in the same commit"; the CI check makes forgetting one of the two impossible, and SKILL.md prose changes that alter phase/freeze semantics are exactly that case.)**
2. **"stdlib-only is doing a lot of work"** — three scripts, no tests? No: the impl-plan must mirror S1–S7 to tests 1:1 per the frozen PRD; the conformance workflow runs them in CI. Carried as a hard requirement, not assumed. **(D5 — carried to impl-plan: the test plan owns S1–S7 fixtures including the negative ones — torn write, forged entry, drifted matrix.)**
3. **"One skill or three?"** — could ship as three skills (state/lint/registry). Rejected: the PRD froze them as one capability (its counter-pass item 1); the components share fixtures, the lint is the freeze-transition's internal step, and the registry is meaningless without state to join against. One skill, one SKILL.md, one reference dir.

---

**Findings ledger:** D1 resolved (byte-hash permanence stated in-design) · D2 resolved (UNMANAGED check named; `cross-artifact-consistency` is the seventh amendment site) · D3 resolved (MAINTAINING.md same-commit rule) · D4 accepted risk (deferred hook reads; revisit trigger = dogfood misses) · D5 carried to impl-plan (1:1 test mirror incl. negative fixtures).
