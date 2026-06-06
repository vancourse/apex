# SDLC Flow

How this plugin's skills and hooks compose into a single workflow. Read this when you want to know *which skill fires at which phase* — the README answers "what's installed" and "how do I install it."

## Where artifacts live (`docs/` convention)

apex's SDLC artifacts have a standard home so each phase knows where to read its input and write its output:

- **Architecture** (project-wide): `docs/adr/000N-*.md` — one ADR per `architecture-design` pass.
- **Per-feature** (one folder per feature, kebab-case slug): `docs/<feature-slug>/prd.md` → `design.md` → `impl-plan.md`. The folder holds the feature's whole freeze-chain in lineage order.

The author steps (`/apex:prd`, `/apex:design`, `/apex:impl-plan`) write to these paths by default and ask for the slug only when the feature name is ambiguous; `spec-view` reads from them.

## Architecture phase (one-time, or amendment-triggered)

This phase runs ONCE at project start and again whenever a feature crosses the existing architecture boundary (triggered by `apex:design-feature` Pass 4 finding incompatible integration).

```
   ┌───────────────────────────────────────────────────────────────┐
   │ ARCHITECTURE (foundational; not per-feature)                  │
   │    apex:architecture-design                                   │
   │      §1 Framework / runtime / language                        │
   │      §2 Persistence + tenancy model                           │
   │      §3 Trust boundaries + auth + data classification         │
   │      §4 Observability + deployment shape                      │
   │      §5 Design system + UI foundation                         │
   │      §6 Branch / release / PR-stack strategy                  │
   │      §7 System-level threat model (STRIDE)                    │
   │      → each pass outputs an ADR in docs/adr/                  │
   │      → FREEZE the architecture                                │
   │                                                               │
   │    apex:adr-review                                            │
   │      5-element audit per ADR: context, decision, alternatives,│
   │      consequences (incl. security + reversibility), status    │
   │      Fires for every ADR (initial set + amendments).          │
   └───────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                  feature work pipeline below ↓
```

Architecture amendments: when `apex:design-feature` Pass 4 finds the feature can't be served by the frozen architecture, STOP the feature work and write an amendment ADR via `apex:adr-review` first. Then resume design against the amended architecture.

## The pipeline

```
                       ┌────────────────────────┐
                       │  USER TASK / PROMPT    │
                       └───────────┬────────────┘
                                   │
                ┌──────────────────▼──────────────────┐
                │  HOOKS (always-on, automatic)       │
                │   • suggest-skill-on-prompt   →     │ injects review-skill reminders
                │   • suggest-skill-on-edit     →     │ on API-surface paths
                │   • guard-security-paths      →     │ on auth/creds/oauth/secrets paths
                │   • guard-dependency-bump     →     │ on lockfiles / dep manifests
                │   • guard-destructive (Bash)  →     │ blocks rm -rf, force-push, --no-verify
                │   • format-on-save (PostEdit) →     │ ruff / prettier
                └──────────────────┬──────────────────┘
                                   │
   ┌───────────────────────────────▼───────────────────────────────┐
   │ 0. SPEC  (when starting a NEW feature — skip for fixes,       │
   │           refactors, debugging)                               │
   │    superpowers:brainstorming  (explore intent — if no PRD yet)│
   │    superpowers:writing-plans  (turn intent into a plan/PRD)   │
   │    apex:prd-review            (7-pass audit: criteria,        │
   │                                scenarios, scope, unknowns,    │
   │                                metric, sequencing, freeze;    │
   │                                + product-overlap + OSS scan   │
   │                                + adversarial counter-pass.    │
   │                                FREEZE the spec at Pass 7.)    │
   └───────────────────────────────┬───────────────────────────────┘
                                   │
   ┌───────────────────────────────▼───────────────────────────────┐
   │ 1. PLAN                                                       │
   │    apex-flow               §1a reconnaissance                 │
   │                              (cost-shape inversion,           │
   │                               codebase recon,                 │
   │                               producer/consumer dual)         │
   │                            §1b adversarial checklist          │
   │                              (min change, alternatives,       │
   │                               critiques, reuse-vs-add)        │
   │                            §1c verify ask vs raw quotes       │
   │                              (4-column audit table)           │
   │    apex:recon              (Recon Brief — promotes §1a to     │
   │                              an artifact: existing            │
   │                              primitives, contracts,           │
   │                              invariants. Esp. on "support     │
   │                              new X" / "shrink X" framings)    │
   │    apex:design-feature     (if NEW feature, not fix —         │
   │                              scenarios + MVP + deferrals +    │
   │                              integration + failure modes +    │
   │                              §6 attack surface,               │
   │                              with overlap + OSS + adversarial)│
   │    apex:threat-model       (if feature accepts external input,│
   │                              handles classified data, or      │
   │                              changes a privilege transition — │
   │                              STRIDE against attack surface,   │
   │                              anchored on ADR-0003 + ADR-0007) │
   │    api-surface-review      (if new endpoint/payload/handler   │
   │                              → run against PROPOSED shape)    │
   │    protocol-first-workflow (if starting new Python component) │
   │    verify-ports            (if copying code from another      │
   │                              repository — schema/UX/format    │
   │                              assumptions are stale by default)│
   └───────────────────────────────┬───────────────────────────────┘
                                   │
   ┌───────────────────────────────▼───────────────────────────────┐
   │ 2. IMPL PLAN  (how to BUILD it — distinct from §1 PLAN which  │
   │                is what to build; frozen design enters here)   │
   │    impl-plan-review        §1 layered PR stack                │
   │                              (≤400 LOC per PR, one layer)     │
   │                            §2 sequencing / dependency order   │
   │                              (foundation → service → API → UI)│
   │                            §3 test plan per layer             │
   │                              (PRD scenarios → integration     │
   │                               tests 1:1)                      │
   │                            §4 rollout strategy                │
   │                              (feature flag / direct deploy /  │
   │                               migration-first / compat window)│
   │                            §5 reversibility (rollback story)  │
   │                            then FREEZE the plan               │
   └───────────────────────────────┬───────────────────────────────┘
                                   │
   ┌───────────────────────────────▼───────────────────────────────┐
   │ 3. IMPLEMENT — write the tests here: scenarios/use-cases →    │
   │    tests 1:1, E2E-tagged → Playwright (apex:test-strategy)    │
   │    test-strategy              (8-layer model, mocking policy, │
   │                                CI tiering, isolation, 17 rules│
   │                                — routes the test-writing)     │
   │    python-review              (Python — routes to topic file) │
   │    typescript-review          (TS / React — same)             │
   │    postgres-review            (Postgres-internal — schema     │
   │                                 design today; indexing,       │
   │                                 migrations, transactions +    │
   │                                 locking, observability        │
   │                                 planned)                      │
   │    multi-tenancy              (tenant-scoped tables, RLS      │
   │                                 policies, cross-tenant FKs — │
   │                                 Postgres RLS ships today)     │
   │    frontend-design            (UI change)                     │
   │    polymorphic-type-modeling  (new variant / event-type)      │
   │    api-surface-review         (re-run on actual code, not     │
   │                                only the proposed shape)       │
   └───────────────────────────────┬───────────────────────────────┘
                                   │
   ┌───────────────────────────────▼───────────────────────────────┐
   │ 4. VERIFY                                                     │
   │    verification-before-completion  "Never declare done        │
   │                                     without proof."           │
   │       • run tests                                             │
   │       • check logs                                            │
   │       • exercise the change in a browser (for UI)             │
   │       • cover golden path AND edge cases                      │
   └───────────────────────────────┬───────────────────────────────┘
                                   │
   ┌───────────────────────────────▼───────────────────────────────┐
   │ 5. PRE-PR ROBUSTNESS GATE                                     │
   │    ai-pre-review-checklist   9 steps: explain, layering,      │
   │                              state ownership, concurrency,    │
   │                              success/failure/fallback,        │
   │                              tests (quality), consumer-       │
   │                              tracing, reviewer-sim, gaps      │
   │    test-coverage-audit       5 passes: PRD↔mirror, layer      │
   │                              discipline, tier discipline,     │
   │                              mock budget, failure-mode        │
   │                              coverage (test SET, vs ai-pre-   │
   │                              review-checklist's per-test)     │
   │    apex:security-review     5 passes: secrets, authn+authz,   │
   │                              input val + output encoding, dep │
   │                              vuln + supply chain, audit log + │
   │                              security observability. Verifies │
   │                              implementation against the       │
   │                              feature's threat model output.   │
   │    pr-discipline §2          full check suite → squash WIPs   │
   │                              to ONE commit per PR             │
   │    api-surface-review        (if API surface touched)         │
   │    python-review / typescript-review                          │
   └───────────────────────────────┬───────────────────────────────┘
                                   │
   ┌───────────────────────────────▼───────────────────────────────┐
   │ 6. OPEN PR                                                    │
   │    pr-discipline §1     ASK BEFORE PUSH — draft by default    │
   │    pr-review-primer     description template                  │
   │                          (what / why-this-shape / flow /      │
   │                           state / concurrency / transport /   │
   │                           success-failure-fallback / tests)   │
   │    review-risk rules    risk note if auth / data / concurrency│
   │                          / billing / external-API touched     │
   └───────────────────────────────┬───────────────────────────────┘
                                   │
   ┌───────────────────────────────▼───────────────────────────────┐
   │ 6b. COPILOT REVIEW                                            │
   │    copilot-review-loop   GraphQL requestReviews mutation      │
   │                          (botIds: ["BOT_kgDOCnlnWA"]) — REST  │
   │                          + gh CLI silently no-op on bots, so  │
   │                          must use GraphQL throughout; verify  │
   │                          landing via GraphQL reviewRequests   │
   │                          query (gh pr view filters bots);     │
   │                          wait ~15 min; address via 6c; re-    │
   │                          request; STOP at NITs-only OR 5      │
   │                          rounds, whichever first              │
   └───────────────────────────────┬───────────────────────────────┘
                                   │
   ┌───────────────────────────────▼───────────────────────────────┐
   │ 6c. ADDRESS REVIEW — reviewer comments (human or Copilot)     │
   │    responding-to-review  every blocker needs a concrete       │
   │                          artifact; every reply maps to a diff;│
   │                          mechanical flagged-line verification │
   │                          before requesting re-review          │
   │    (For Copilot specifically, the request → wait → address →  │
   │     rerequest cycle terminates per 6b's cap: NITs-only OR     │
   │     5 rounds, whichever first.)                               │
   └───────────────────────────────┬───────────────────────────────┘
                                   │
   ┌───────────────────────────────▼───────────────────────────────┐
   │ 7. REVIEW  (yours or others')                                 │
   │    pr-discipline §4     SINGLE PR scope — no historical crawl │
   │                          target 2-3 min of agent work         │
   │    python-review / typescript-review                          │
   │    api-surface-review   (if API surface in the diff)          │
   └───────────────────────────────┬───────────────────────────────┘
                                   │
   ┌───────────────────────────────▼───────────────────────────────┐
   │ POST-TASK: SELF-IMPROVEMENT LOOP                              │
   │    memory-note   capture surprising / non-obvious lessons     │
   │                  → ~/.claude/.../memory/<name>.md             │
   │                  → ~/.claude/domain-knowledge/<project>.md    │
   └───────────────────────────────────────────────────────────────┘
```

## Side paths (not phase-sequential)

**DEBUG.** When a bug, test failure, or unexpected behavior interrupts any phase above, drop into `superpowers:systematic-debugging` (root-cause-first / reproduce-first / log-first discipline). Apex deliberately defers — the systematic-debugging skill is a complete discipline and we don't duplicate it. Once the bug is understood, return to whatever phase you were in.

**ADVERSARIAL PAIR.** `apex:prd-review` and `apex:design-feature` both include inline adversarial counter-passes for the cheap (one-agent) version. For non-trivial PRDs or designs, dispatch the heavier two-agent version via `superpowers:dispatching-parallel-agents` — one cooperative, one adversarial, both running the same apex skill on the same input. **Run the pair at the *design-shape* gate (`apex-flow` §1b / `apex:design-feature`), not only at `impl-plan-review`** — the "is this the minimal design?" decision is made at the shape gate, so a pair that first runs at `impl-plan-review` arrives after the shape is already locked (the exact failure mode `apex:recon` + the §1b pair are meant to catch). The user's CLAUDE.md may also prescribe this pattern for finished PRs (independent review).

## Skill × Phase matrix

Phases shorthand: SPEC=0, PLAN=1, IMPL-PLAN=2, IMPL=3, VERIFY=4, PRE-PR=5, OPEN=6, COPILOT=6b, ADDRESS=6c, REVIEW=7.

```
                              SPEC  PLAN  IMPL-PLAN  IMPL  VERIFY  PRE-PR  OPEN  COPILOT  ADDRESS  REVIEW
prd-review                     ✓
apex-flow                            ✓
recon                                ✓¹¹
design-feature                       ✓⁷
threat-model                         ✓⁸
impl-plan-review                            ✓
test-strategy                               ✓         ✓
api-surface-review                   ✓                ✓                ✓                                  ✓¹
python-review                                         ✓                ✓                                  ✓
typescript-review                                     ✓                ✓                                  ✓
postgres-review                                       ✓                ✓                                  ✓
multi-tenancy                        ✓                ✓                ✓                                  ✓¹⁰
frontend-design                                       ✓²
protocol-first-workflow              ✓³               ✓³
polymorphic-type-modeling            ✓⁴               ✓⁴
verify-ports                         ✓⁵               ✓⁵
verification-before-completion                                ✓
ai-pre-review-checklist                                              ✓
test-coverage-audit                                                  ✓
security-review                                                      ✓⁹
pr-discipline                                                        ✓      ✓                                    ✓
pr-review-primer                                                            ✓
copilot-review-loop                                                                ✓
responding-to-review                                                                                ✓⁶
memory-note                                                                                                          after

superpowers:systematic-debugging   — side path; fires on bug discovery (any phase)
superpowers:brainstorming          — upstream of SPEC (intent exploration)
superpowers:writing-plans          — upstream of IMPL-PLAN (writes the plan; review with apex:impl-plan-review)
superpowers:dispatching-parallel-agents — mechanism for the heavier two-agent adversarial pair pattern (see Side paths)

apex:cross-artifact-consistency    — fires at the impl-plan-freeze boundary (after IMPL-PLAN, before IMPL): checks the frozen PRD↔design↔plan still agree (DROPPED / ORPHAN / CONFLICT)
apex:incident-retro                — side path; post-release, on a RESOLVED incident — maps the miss to the gate that should have caught it, feeds domain-knowledge via memory-note
```

¹ if API surface in diff
² UI changes only
³ new Python component
⁴ new variant / event-type / discriminated union
⁵ porting / adapting code from another repository
⁶ when addressing reviewer comments on an open PR (human or Copilot)
⁷ NEW feature design (not fix) — distinct from `apex-flow` §1b which covers fixes + refactors generically
⁸ when the feature accepts external input, handles classified data, or changes a privilege transition
⁹ for any PR touching auth / data access / external input / cryptography / sensitive paths
¹⁰ when touching tenant-scoped tables, RLS policies, or cross-tenant FK enforcement
¹¹ promotes apex-flow §1a to a written Recon Brief; fires on design-bearing work, esp. "support new X" / "shrink X" framings
(architecture-design + adr-review are foundational, not per-feature — see "Architecture phase" section above)

## Scenario → test traceability: where each part is validated

Validation is **distributed across the freeze gates, one link per phase** — each part is checked at the gate of the phase that *owns* it. There is no single "validate everything" step; the chain converges at PRE-PR.

| Part | Validated at | Phase | Asserts |
|---|---|---|---|
| Scenarios exist (≥3, edge cases) | `prd-review` Pass 2 | SPEC | PRD owns a testable scenario list |
| Each scenario **tagged** (integration / E2E) | `prd-review` Pass 2 | SPEC | Highest verification layer declared (tag conservatively) |
| Compound scenarios **decomposed** into use-case one-liners | `prd-review` Pass 2 | SPEC | Only when compound; simple scenarios stay atomic |
| Each layer cites **the scenario(s)/use-case(s) it serves** | `impl-plan-review` Pass 3 | IMPL-PLAN | layer→scenario lineage present |
| Every scenario has an **owner PR**; every E2E tag has a **spine-E2E owner** | `impl-plan-review` Pass 3 | IMPL-PLAN | The plan *covers* the spec, browser layer included |
| Tests **mirror scenarios 1:1** | `test-coverage-audit` Pass 1 | PRE-PR | Tests exist and name their scenario |
| E2E-tagged scenario has a **real Playwright test** | `test-coverage-audit` Pass 1 | PRE-PR | Not "an integration test wearing an E2E costume" |
| Each **use-case → ≥1 named assertion** | `test-coverage-audit` Pass 1 | PRE-PR | Assertion-level floor of the mirror |
| Right layer / mock budget / CI tier / failure modes | `test-coverage-audit` Pass 2–5 | PRE-PR | Test architecture is sound |
| Per-test **quality** | `ai-pre-review-checklist` Step 6 | PRE-PR | Tests are meaningful, not boilerplate |
| **It actually works** (tests run green, behavior proven) | `verification-before-completion` + CI | VERIFY | Execution proof, not just artifact review |

**Two kinds of validation, kept separate:** gates above the VERIFY row are **artifact reviews** (*does the doc/plan/test-set claim the right coverage?* — cold reads at the freeze gates). The VERIFY row is **execution proof** (*does it run green?*). A test that mirrors a scenario (PRE-PR) is not the same as a test that passes (VERIFY).

**Convergence point:** `test-coverage-audit` Pass 1 is the single place the whole spec→test mirror is walked in both directions (no orphan scenario, no gold-plated test). Upstream gates validate the *plan* will satisfy it; this validates the *code* did.

**The execution-time link (designed, not yet built):** that the chain also holds at *runtime* — every scenario/use-case actually built and merged, nothing lost to an executor — is the **bead-coverage audit + Witness gate** from `docs/execution-tiers/` (apex × Gastown). Pre-execution validation = the freeze gates above; execution-time validation = the bead audit.

## Eight principles overlaid on the pipeline

1. **Plan before coding** — never skip phase 1; re-enter it mid-task if the design breaks. For NEW features, phase 0 (SPEC) + phase 2 (IMPL-PLAN) are both required upstream gates.
2. **Multi-phase rule** — `api-surface-review` runs at PLAN, IMPL, AND PRE-PR. Invoking it once does not discharge later gates. Design intent and code reality diverge between phases; the later passes catch the drift.
3. **Prove it works** — phase 4 (VERIFY) is non-negotiable. Verification is what separates "the code exists" from "this is done."
4. **Ask before push** — every transition from local → remote requires explicit user confirmation. Default to `--draft` on PR creation.
5. **Self-improvement loop** — every non-obvious lesson goes into memory or domain-knowledge so the next session starts smarter.
6. **Loop termination** — the COPILOT review (phase 6b) and human-review address cycle (phase 6c) both terminate at NITs-only OR 5 rounds. Five rounds with non-NIT issues outstanding = the PR shape is wrong; return to an upstream gate (IMPL-PLAN, design, or PRD).
7. **Freeze gates** — the architecture freezes after `apex:architecture-design` (7 ADRs); the PRD freezes after `apex:prd-review` Pass 7; the implementation plan freezes after `apex:impl-plan-review`. All three freezes mean "scope changes from this point require explicit amendment, not silent reinterpretation." Per-feature work runs against frozen upstream artifacts.
8. **Security is structural, not ceremonial** — `apex:architecture-design` Pass 3 (trust boundaries + auth + data classification) and Pass 7 (system-level threat model) set the security invariants ALL future features inherit. `apex:threat-model` applies STRIDE per-feature against those invariants. `apex:security-review` audits the implementation against the threat model at PR time. The hook `scan-secrets-on-edit` BLOCKS writes that contain real-looking secrets. Security checked at design beats security checked at PR; security checked at PR beats security found in prod.

## When to skip phases

The pipeline assumes a non-trivial NEW-feature change. For trivial or non-feature work, drop phases:

| Change type | Phases that fire |
|---|---|
| Typo / single-line fix / obvious bug | 3, 4, 6 (skip 0 SPEC, 1 PLAN, 2 IMPL-PLAN, 5 PRE-PR) |
| Internal refactor with no API change | 1 (light), 3, 4, 5, 6, 7 (skip 0 SPEC, 2 IMPL-PLAN, api-surface-review) |
| Fix / refactor of existing behavior | 1 (run `apex:recon` first if design-bearing / unfamiliar area), 3, 4, 5, 6, 7 (skip 0 SPEC — no new spec; skip 2 IMPL-PLAN unless the fix touches >1 layer) |
| NEW endpoint / payload / handler | 0, 1, 2, 3, 4, 5, 6, 6b, 6c, 7 — all phases, all skills |
| NEW feature from scratch | all phases (0 → 7), full freeze-gate chain (spec → design → plan) |
| Doc / comment-only update | 6 only (still ask before push; Copilot review optional per `apex:pr-discipline`) |
| Reviewing someone else's PR | 7 only |

When in doubt, run the gate. The cost is one skill invocation; the cost of skipping is multiple review cycles or a misshapen feature.
