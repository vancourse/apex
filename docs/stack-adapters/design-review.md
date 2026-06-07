# apex:design-review — stack-adaptive bug-loop MVP (PR-A + PR-B)

**Artifact:** `/Users/raviv/devenv/apex/docs/stack-adapters/design.md` · **Against:** FROZEN PRD `/Users/raviv/devenv/apex/docs/stack-adapters/prd.md` · **Method:** six cold lenses (AC-coverage, API-surface, compose-with-gate/parent-child, threat-model/STRIDE, MVP-scope/integration, full 5+1) synthesized by the freeze gate. Every load-bearing citation independently re-verified at HEAD.

**VERDICT: FREEZE-READY.** All blockers and all valid NITs are fixed in-place; the revised design is internally consistent and every cite is true at HEAD. The structural spine (per-axis contract, two-binding resolver, P3→P4 seam, compose-not-duplicate via the gate's allowlist) survived all six attack lenses unbroken — no element was strikeable without losing an AC, and no gate rail is re-implemented.

## Per-pass verdict (5+1, attack lens, synthesized)

| Pass | Verdict | Notes |
|---|---|---|
| **1 — Scenarios** | PASS | All 10 PRD scenarios + sub-scenarios (S1.2/S2.1/S5.1/S5.2/S9) map to a named mechanism; AC↔scenario mirror (`prd.md:67`) holds. |
| **2 — MVP cut** | PASS | §F.1 self-strike is genuine (re-run): striking obs adapter breaks AC4's ≥2-axes proof; striking two-binding re-introduces MCP-only-dies-headless. `secret_ref` is reserved-schema forward-compat, **and MVP detect-stack no longer auto-writes it** (F3 fix). |
| **3 — Deferrals** | PASS | PR-C/D/E + `secret_ref` resolution; none hot-fix-bites in 24h (grep+gh are deliberate universal backends). |
| **4 — Integration / invariants** | PASS (was the blocker locus) | compose-not-duplicate is structural (write affordance absent from the gate's invocation-#1 allowlist). The two integration blockers (recon-precedent false cite; README tables hedged) are fixed. |
| **5 — Failure modes** | PASS | §I thorough; `query_logs → []` is valid-empty not swallow; smuggled-token-on-read handled; the diagnosis heuristics now flagged impl-plan-deferred with bounded-worst-case contracts. |
| **6 — STRIDE** | PASS (was NOT-clean; now closed) | F1/F2/F3 + G1/G2 all landed as design deltas. See table below. |

## API-surface verdict (§A/§B/§C — the U2 highest-cost decision)

**PASS.** Per-axis-vs-uniform is correctly justified (uniform `query(verb,args)` is the Pass-4 "docstring needs an `and`" failure and defeats S9). Producer-side normalization is the chosen seam (investigate-bug never parses raw `gh --json`/grep). Bounded-window required-positional is the Pass-3 DoS guard. Error shape is human+machine only. **"MCP-only is structurally impossible" holds** — the unattended branch never references `axis_cfg.mcp`; S5.2 tests it. Fixes applied at freeze: `CommitRef` now has a field table; all 5 `AdapterError` codes route to a named terminal; `comment` return type unified to `-> None`; `tracker.comment` P5 mis-attribution corrected (it is a downstream-consumer post-handoff verb, called by neither investigate-bug nor the gate); `LogLine.source` justified MVP-real (multi-path/stream grep); resolver liveness-probe helpers given one-line contracts.

## STRIDE table

| Category | Vector | Verdict | Mitigation / residual |
|---|---|---|---|
| Spoofing | compromised MCP / `kind` flip | PASS | `kind` not a trust signal; compromised-MCP residual bounded by red-test-required-to-reach-P4; unattended uses CLI only. |
| Tampering | profile in CI (descriptor fields) | PASS | value-shape allowlist, shape-validate-on-read; `cli` no-separators. |
| Tampering | profile in CI (`log_path` = file read) | **PASS (F1 fixed)** | new `repo_path` field-kind: no `..`, realpath under repo root + console-adapter confinement. Was the one AC1-not-decidable field. |
| Tampering | pre-fence derivation injection | **PASS (F2 fixed)** | grep `query` is escaped-literal (closes ReDoS); `derive_window`/`paths_guess` worst case is wrong-but-bounded plan caught by gate Stage-A on `PLAN.json`. |
| Repudiation | — | PASS | inherited gate terminals, each emits a structured artifact. |
| Info disclosure | `secret_ref` / bundle leak | **PASS (F3 fixed)** | MVP no longer auto-populates `secret_ref` (env-var-NAMES probe deferred to PR-C); reporter-PII residual correctly named (gate leak-scan guards out-sinks). |
| DoS | log query amplifier | PASS | bounded window (volume) + escaped-literal query (pattern/ReDoS). |
| EoP | malicious/absent adapter | PASS + named residual | agent-tool layer: no write affordance (gate owns P4). **G1 named:** adapter code is process-privileged, not allowlist-bounded — accepted, first-party-only in MVP. |
| EoP | routing to wrong service / remote-URL injection | PASS | descriptor-vs-operation distinction; **G2 named** (`git remote get-url` sink adequate because `repo`/`host` stay descriptors). |

## Integration verdict

**PASS** after the two blocker fixes. Command #15 menu sweep is exact (six count-sites verified; registry `MAINTAINING.md:43-52`, recipe block `:58-61`). FLOW.md placement correct (side-path after AUTONOMOUS BUG-FIX `:260`, matrix `:305`). help.md placement correct. **Now also closed:** the recon false-precedent (replaced with the true `autonomous-fix`/`incident-retro` by-name-only precedent); the README Skills + Commands tables stated as **required** edits with anchors (not "if"); the `--exclude-dir=.claude` recipe guard for the stale worktree (7 false hits confirmed); the §H carry-back now names all three sites (`prd.md:5`, `prd.md:154`, `SKILL.md:29`) against the gate PRD's *actual* "two children, parent of both" wording — not the strawman "direct child."

## Citation integrity

Zero false load-bearing citations remain. Independently re-verified at HEAD: `commands/`=14; six count-sites (README:59/222/233, help.md:10/61, WALKTHROUGH:100); MAINTAINING registry :43-52 + recipe block :58-61; autonomous-fix seam (B2:35, P2:57-63, P3:65-71, P4:73-79, terminals:89-100, cost:51-55, nonce:176-191, U9:151, one-hop:155, children:29); gate PRD:5 + :154 ("two children, parent of both"); stack-adapters PRD supersede already decided :111/:117/:121; BookBridge `auto-fix-bug.yml` exists; `skills/setup/` correctly absent; recon IS a slash command (the corrected fact). The design also corrects two loose cites in its own frozen PRD (MAINTAINING `:47-52`, README `:233`).

## Freeze readiness

**FROZEN.** No blocker remains. Build order per §K: api-surface-review (done, §A) → PR-A → PR-B (strict). Next gate: `apex:impl-plan`.
