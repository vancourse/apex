# Changelog

All notable changes to apex are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added

- **`docs/research/sdlc-frameworks-survey.md`** — a 5-angle deep-research survey of other SDLC frameworks, AI-coding harnesses, and methodologies, filtered against apex's lean/adversarial thesis: ranked adopts (cross-artifact consistency, expand-contract migrations, incident-retro, pre-mortem, AI-code supply-chain checks, Shape Up appetite/circuit-breaker, observability/privacy gates, WCAG 2.2 a11y), cheap tightenings, and an explicit "tempting but reject" list (BMAD persona-swarm, ECC's 249-skill catalog, SBOM/Sigstore tooling, DORA measurement, SAFe/WSJF, full ASVS/PASTA).
- **`docs/cross-artifact-consistency/` + `docs/incident-retro/` — two dogfooded specs through the full SPEC + DESIGN chain (PRD → prd-review → FROZEN → design → design-review → FROZEN).** The top two *structural* gaps the survey found, run through apex's own gates: a read-only **cross-artifact consistency analyzer** (does the frozen PRD↔design↔impl-plan still agree? — apex's "horizontal" blind spot; reuses the 0.3.2 scenario-IDs + layer→scenario lineage as its mapping anchor) and **`incident-retro`** (the missing *post-release* learning loop — map a resolved incident to the apex gate that should have caught it via `FLOW.md`, feed the lesson to `domain-knowledge` through `memory-note`; learning half only, not incident response). **Design only — not yet built** (impl-plan is the next gate). The design reviews bit: scoped CONFLICT-detection to a deterministic MVP, added a path-traversal mitigation, a cause-unknown→debugging boundary, and a PII-in-lesson guard. Both specs dogfood the new scenario-tagging + use-case-decomposition features.
- **README "Install by asking Claude" subsection.** A copy-paste paste-to-install block: drop it into any Claude Code session and Claude runs the `claude plugin marketplace add vancourse/apex` → `install apex@apex` → confirm sequence, then reminds you to restart and `/apex:help`. apex is public/MIT, so no auth or org membership is required (unlike a private plugin). Also corrects a stale entry-point command count (~11 → 13).

### Changed

- **Docs: clarify `apex-flow` as the umbrella gate + where tests get written.** WALKTHROUGH's `/apex:flow` catch-all note now explains that `apex-flow` is the **umbrella gate for any non-trivial change** (the home for fixes/refactors that aren't a clean new feature), running §1a reconnaissance + §1b adversarial design checklist + §1c verify-the-ask, then routing to the specialist gate. FLOW.md's IMPLEMENT box now reads "write the tests here: scenarios/use-cases → tests 1:1, E2E-tagged → Playwright" — closing the drift left after the scenario→test-layer traceability change (the box still said "PRD scenarios → integration tests 1:1"). Also fixes a stale entry-point command count in WALKTHROUGH (~11 → 13).

---

## [0.3.2] — 2026-06-06

### Added

- **`INTEROP.md` — Spec Kit / BMAD interop guide.** apex composes with [GitHub Spec Kit](https://github.com/github/spec-kit) and [BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD): author specs with them, then run apex's adversarial review/freeze gates on their artifacts. Includes the phase→gate mapping (their `spec.md`/`plan.md`/`tasks.md` / `docs/prd.md`/`docs/architecture.md` → apex's `prd-review`/`design-review`/`impl-plan-review`/`adr-review`/`threat-model`), the interleaved workflow, and a "don't double-author" rule. Linked from the README header.
- **`docs/execution-tiers/` — apex × Gastown handoff design (design docs).** A dogfooded PRD → design (authored *and* reviewed through apex's own gates) for a thin, executor-agnostic handoff: tier-select an executor (Gastown fleet → superpowers → baseline single-agent), keep apex's review gates **tier-invariant** (gate each unit before the Refinery merges it), and optionally project the frozen impl-plan into a bead lineage graph so "nothing lost" becomes a checkable coverage audit. Design only — not yet built.

### Changed

- **Scenario → test-layer traceability (closes the E2E seam).** The PRD↔test 1:1 mirror was enforced only at the integration layer; which scenarios got promoted to browser E2E was left to implementation-time judgment. Now it's traced end-to-end with no new artifact or command:
  - **`prd-review` Pass 2** — each PRD scenario is **tagged with its highest verification layer**: default *integration* (`test-strategy` Layer 4); the critical-path subset additionally tagged **E2E** (Layer 6 spine, Playwright). Tag conservatively.
  - **`impl-plan-review` Pass 3** — each layer/PR now names **the PRD scenario(s) it serves** (layer→scenario lineage), and every **E2E-tagged** scenario gets an owner PR for its spine-E2E (Playwright) test *in addition to* its integration test. New adversarial check for an E2E-tagged scenario whose only owner is an integration test.
  - **`test-coverage-audit` Pass 1** — adds an **E2E-tag check**: an E2E-tagged scenario with only an integration test is a coverage gap; plus an adversarial check for an "integration test wearing an E2E costume" (asserts the API result but never drives the UI flow).
- **Conditional use-case decomposition.** A *compound* PRD scenario (one that does more than one user-visible thing) may break into **sub-numbered one-liner use-cases** (`S2` → `S2.1`, `S2.2`…) — the finer, vertical cross-reference anchor between scenarios and the horizontal impl-plan layers. Simple scenarios stay atomic (YAGNI guard — no `S-dot` busywork). `impl-plan-review` Pass 3 cites layers at use-case granularity (`serves S2.1, S2.3`); `test-coverage-audit` Pass 1 mirrors each use-case to ≥1 named assertion. One-liners only — not a full use-case spec (actors/preconditions/alternate flows stay out of scope). Doubles as the natural bead-task granularity for the `docs/execution-tiers` handoff.
- **`FLOW.md` — "Scenario → test traceability: where each part is validated."** A new subsection (after the Skill × Phase matrix) mapping each part of the chain to the gate + phase that validates it (`prd-review` → `impl-plan-review` → `test-coverage-audit` → `verification-before-completion`), the artifact-review vs. execution-proof split, the convergence point (`test-coverage-audit` Pass 1), and the execution-time link (the `docs/execution-tiers` bead-coverage audit). The canonical home for "where does each part get checked?"
- **README + WALKTHROUGH** — the `prd-review` / `impl-plan-review` / `test-coverage-audit` skill-table rows and the WALKTHROUGH phase table now reflect scenario tagging, use-case one-liners, the layer→scenario lineage, and the E2E/Playwright owner requirement.

---

## [0.3.1] — 2026-05-31

### Added

- **`/apex:setup` command** — guided installer for apex's recommended companions. Detects what's already present, installs what it safely can via Bash, and prints exact `/plugin` / package-manager commands for the rest: the SDLC companions (`superpowers`, `pr-review-toolkit`, `frontend-design`) that the chaining commands depend on, plus an optional **large-codebase context tool**. The 13th `[USER]` entry-point command.
- **Large-codebase context tools section (README)** — documents three third-party structural-index options so Claude navigates by structure instead of re-grepping the tree each session: **Graphify** (committed AST knowledge graph + PreToolUse hook), **Serena** (live LSP symbol navigation), **Claude Context** (semantic vector search). Includes the staleness rule (index = navigation aid, not ground truth).

### Changed

- **Frontend rules: animation discipline.** `rules/frontend.md` and `apex-flow` §11 (Frontend Hygiene) now require that motion-library animations (Framer Motion / Motion, etc.) be gated behind `prefers-reduced-motion` and reuse the existing animation pattern rather than introducing a parallel one — folding the one durable idea from the "animated website" workflow into apex's existing accessibility discipline.
- **`recon` Step 1 now requires a code graph on large/unfamiliar repos** (strengthened from "if present"). The structural index is the precondition for trustworthy enumeration: build/refresh one (Graphify / Serena / Claude Context; `/apex:setup` if none) before enumerating, then query it instead of grepping blind. Discipline preserved: the graph answers Step 1 (*where it lives*), never Step 2 (*the contract*), and is **ephemeral** (regenerated, never trusted as stored truth) — mirroring apex's structural-ephemeral / semantic-durable split. Small/familiar trees still use plain grep/Explore (no index for a handful of files).
- **`apex-flow` §1a + the design-entry hook now nudge the graph precondition** — on a large/unfamiliar repo, the "codebase reconnaissance" look should go through an index (built via `/apex:setup` if absent), not blind grep, before design-bearing work.
- **README licensing note** — clarifies apex **bundles none** of the companions or context tools: they are independent third-party projects under their own licenses, only referenced/recommended; apex itself is MIT.
- README *Recommended companions* now lists `pr-review-toolkit` explicitly (backs `/apex:review-pr`) and points at `/apex:setup`.

---

## [0.3.0] — 2026-05-31

### Changed

- **BREAKING — streamlined the slash-command names.** The `/apex:` menu names are now shorter and named by phase/artifact. **Skill names are unchanged** (e.g. `/apex:design` invokes the `design-feature` skill); only the slash commands were renamed. Update any `~/.claude/CLAUDE.md` stubs or muscle memory:

  | Old | New |
  |---|---|
  | `/apex:apex-flow` | `/apex:flow` |
  | `/apex:create-prd` | `/apex:prd` |
  | `/apex:architecture-design` | `/apex:arch` |
  | `/apex:design-feature` | `/apex:design` |
  | `/apex:create-impl-plan` | `/apex:impl-plan` |
  | `/apex:copilot-review-loop` | `/apex:copilot-review` |
  | `/apex:memory-note` | `/apex:remember` |

  `recon`, `review-pr`, `spec-view`, `test`, `help` are unchanged. Menu stays 12.

- **Every author → review → freeze handoff in the SDLC chain is now enforced, not merely flow-prescribed.** Previously a drafted artifact (PRD, ADR set, design, impl plan) could slide into the next phase without its load-bearing cold review actually running. Now each gate is enforced with defense-in-depth — a mandatory hand-off in the author step, a downstream hard-gate in the next phase, and a cross-prompt backstop in the `suggest-skill-on-prompt` hook — with **no new slash commands** (the reviews stay `[AUTO]` skills; the menu remains 12).
  - **PRD → `prd-review` → design:** `commands/prd.md` now requires `prd-review` + freeze before designing (was "suggest, don't auto-invoke"); `skills/design-feature/SKILL.md` adds a **hard prerequisite** — stop if the PRD isn't frozen via `prd-review`.
  - **Architecture → `adr-review` → freeze:** `skills/architecture-design/SKILL.md` freeze-readiness now **mandates each of the 7 ADRs pass `adr-review`** before the architecture freezes (ADRs are authored, not frozen, until audited).
  - **Design → `design-review` → impl-plan:** `skills/design-feature/SKILL.md` mandatory "next step — `apex:design-review`" section (the cold adversarial re-pass + freeze, distinct from the cheap inline counter-passes); `commands/impl-plan.md` prerequisite requires the design **FROZEN via `design-review`**, not just drafted.
  - **Impl plan → `impl-plan-review` → build:** `commands/impl-plan.md` now requires `impl-plan-review` + freeze before any implementation (was "suggest, don't auto-invoke").
  - `hooks/suggest-skill-on-prompt.sh` gains **three phase-freeze gates** — entering design (→ `prd-review`, plus a **conditional `recon` nudge** for non-trivial / unfamiliar work, beyond the existing subtractive-trap nudge), entering impl-planning (→ `design-review`), entering build/code (→ `impl-plan-review`) — each firing on the prompt that signals the transition. `skills/design-feature/SKILL.md` "When to invoke" also prompts `recon` first for non-trivial / unfamiliar changes (skip for trivial/familiar — its own YAGNI guard).

### Added

- **Standard `docs/` layout for SDLC artifacts** (was: "ask the user where to save"). Architecture stays project-wide at `docs/adr/000N-*.md`; per-feature artifacts live in one folder per feature — `docs/<feature-slug>/prd.md` → `design.md` → `impl-plan.md` — keeping a feature's whole freeze-chain together in lineage order. `/apex:prd` / `/apex:design` / `/apex:impl-plan` write to these paths by default (asking for the slug only when ambiguous), `spec-view` reads from them, and `FLOW.md` documents the convention canonically.

---

## [0.2.1] — 2026-05-31

### Added

- **`recon` command + skill** (`commands/recon.md`, `skills/recon/SKILL.md`) — "reconnaissance brief before design." Promotes `apex-flow` §1a from an in-head checklist into a first-class, artifact-producing step: scoped to the change's blast radius, it enumerates the authoritative primitives that already answer the design's questions, distills their **contracts (not signatures)**, captures invariants + trust boundaries, runs the producer/consumer + first-affordance checks against that fact base, and persists durable semantic facts to `domain-knowledge`. Output is a short Recon Brief that feeds `design-feature` / §1b. The 12th `[USER]` entry-point command.
- **Auto-firing of recon on subtractive-design traps** — `hooks/suggest-skill-on-prompt.sh` gains a `UserPromptSubmit` block that nudges `apex:recon` when a prompt matches trap framings (`shrink` / `bloated` / `support a new scope/source/kind/variant` / `add a flag/field/enum`) — the framings that most reliably hide an existing primitive and pull toward additive machinery.
- **`apex-terse` output style** (`output-styles/apex-terse.md`) — an optional, scoped terse mode. Trims wrapper prose (preamble, transitions, task-restatement, post-hoc summaries) while **exempting** apex's load-bearing zones — adversarial counter-passes, per-finding `file:line` evidence, and freeze/decision rationale — which expand to whatever the argument needs. Ships as a user-level Claude Code output style (copy-installed), since a plugin can't contribute one as active context.

### Changed

- **Slash menu trimmed to the entry-point commands.** The 22 `[AUTO]` commands were removed as *slash commands* — they are still skills and still fire automatically (driven by their `SKILL.md` description + the `suggest-skill-*` hooks); only the typed `/apex:` alias is gone. With the new `recon`, the menu is **12** typed entry points: `apex-flow`, `create-prd`, `architecture-design`, `recon`, `design-feature`, `create-impl-plan`, `review-pr`, `copilot-review-loop`, `spec-view`, `test`, `memory-note`, `help`. To run an auto gate manually, ask for it by name. README / HOWTO / WALKTHROUGH / `help` cheat sheet updated accordingly (auto gates are now referenced by bare skill name, not `/apex:<name>`).
- **`apex-flow` §1b — adversarial pair is now the DEFAULT for non-trivial shape decisions**, run at the design-shape gate (§1a/§1b / `design-feature`) *before* `impl-plan-review`, not only at impl-plan-review (by which point the shape is already locked). §1a also gains a "promote to `apex:recon` when the work is design-bearing" note. `FLOW.md` adds recon to the PLAN box + Skill × Phase matrix + skip-table, and moves the adversarial-pair guidance to the design-shape gate. `rules/principles.md` adds recon to the applied-principles table (producer/consumer dual, first-affordance, pure-addition smell).

---

## [0.2.0] — 2026-05-29

### Added

- **`design-review` skill + command** — the author/review split for the design phase, mirroring what PRD, ADR, and impl-plan already have. A 6-pass *adversarial* re-pass (scenarios / MVP cut / deferral list / integration / failure modes / attack surface) run cold in a separate cognitive step from `design-feature`'s steelman authoring voice, plus an explicit design-freeze ceremony (the gate between "design drafted" and "impl plan may begin"). The 2-agent cooperative+adversarial pair (`superpowers:dispatching-parallel-agents`) is the default for non-trivial designs.
- **`spec-view` skill + command** — renders a frozen (or freeze-candidate) PRD / ADR set / design doc as a **disposable, fully-offline rich-HTML view** for human freeze-review: color-coded freeze-readiness dashboard, inline-SVG data-flow / STRIDE / MVP-vs-deferred diagrams, collapsible review passes, severity badges, syntax-highlighted code. Markdown stays canonical; the HTML is a throwaway view in `tmp/apex-views/` (gitignored, never re-ingested by downstream skills).
- **Orchestration commands** — `/apex:prd` (chains `superpowers:brainstorming` → `writing-plans`), `/apex:impl-plan` (chains `superpowers:writing-plans`), and `/apex:review-pr` (dispatches 6 `pr-review-toolkit` specialist agents in parallel).
- **`/apex:test [layer]`** — a router that focuses `test-strategy` on a single test layer: pass an industry term (`unit` / `integration` / `smoke` / `e2e` / `component` / `visual` / `drift`) or an apex layer name and get that layer's what-to-test + mock policy (budget ≤2) + CI tier, mirroring the "what people mean by X" mapping already in `test-strategy`. Advisory only — it does **not** execute the suite (the runner is project-specific). No argument prints the 8-layer menu.
- **`/apex:help`** — prints the command cheat sheet (which commands are user-typed vs. auto-fired, plus the SDLC workflow at a glance).
- **`WALKTHROUGH.md`** — a top-level narrative guide taking a user from an idea to a shipped product or feature *in order*: a three-rule mental model (author + review/freeze pairs, frozen-artifact-as-contract, ~6 user-typed commands), the two entry points (greenfield product vs. feature in an existing product), a phase-by-phase table (which `[USER]` command enters each phase, which `[AUTO]` skills fire inside it, and the freeze gate before moving on), and explicit skip rules for small work. The narrative companion to `FLOW.md`'s reference map; surfaced from the README header and the `/apex:help` deeper-docs list.
- **`[USER]` / `[AUTO]` description tags** on every command — the slash menu now signals whether you type a command at a phase boundary (`[USER]`) or the model fires it automatically based on phase + file paths (`[AUTO]`).

### Changed

- README gains a **Commands** section documenting the user-facing slash commands and the `[USER]`/`[AUTO]` tag convention; the `design-review` and `spec-view` skills are added to the Skills table.
- `test-strategy` now cross-references **`superpowers:test-driven-development`** — making explicit that apex defers the red-green TDD loop (write the failing test first) to that side-path companion and owns only the scaffolding *around* it (scenario sourcing, 8-layer placement, mock budget). The cheat sheet (`/apex:help`) surfaces the same pointer in its Testing workflow line.

---

## [0.1.0] — 2026-05-18

Initial public release.

### Skills

| Skill | What it does |
|---|---|
| `apex:architecture-design` | 7-pass foundational architecture review (framework / persistence + tenancy / trust boundaries + auth / observability + deploy / design system / branch + release / system-level threat model). Each pass outputs an ADR. |
| `apex:adr-review` | 5-element ADR audit (context, decision, alternatives ≥2, consequences incl. security + reversibility, status). |
| `apex:prd-review` | 7-pass PRD audit with spec-freeze gate + product-overlap + OSS-alternatives + adversarial counter-pass. |
| `apex:apex-flow` | Umbrella planning gates: §1a reconnaissance + §1b adversarial checklist + §1c raw-quote audit. |
| `apex:design-feature` | Feature design from scratch (scenarios + MVP + deferrals + integration + failure modes + §6 attack surface). |
| `apex:threat-model` | Per-feature STRIDE threat model at design time, anchored on architecture ADRs. |
| `apex:impl-plan-review` | 5-pass implementation plan review (layered PR stack ≤400 LOC, sequencing, test plan, rollout, reversibility). |
| `apex:test-strategy` | 8-layer test methodology (Unit / Service-real-DB / Router-contract / Backend-scenario / FE-component / Spine-E2E / Visual-E2E / Drift) + mocking policy + CI tiering + 17 design rules. |
| `apex:test-coverage-audit` | Pre-PR audit: PRD↔mirror, layer discipline, CI tier discipline, mock budget, failure-mode coverage. |
| `apex:security-review` | PR-time 5-pass security audit: secrets, authn+authz, input val + output encoding, dep vuln + supply chain, audit log. |
| `apex:python-review` | Generic Python rules with routing table to 11 topic files. |
| `apex:typescript-review` | Generic TypeScript/React rules with routing table to 15 topic files. |
| `apex:postgres-review` | Generic PostgreSQL rules — schema design today; indexing, migrations, transactions + locking, observability planned. |
| `apex:multi-tenancy` | Multi-tenant isolation — Postgres RLS today; schema-per-tenant, DB-per-tenant, app-layer filtering, tenant-context propagation planned. |
| `apex:api-surface-review` | 5-pass API surface review from the consumer's perspective. |
| `apex:ai-pre-review-checklist` | 9-step pre-PR robustness gate (branch explanation, layering, state, concurrency, fallback, tests, consumer-tracing, reviewer sim, gaps). |
| `apex:verification-before-completion` | Phase 3 gate — prove the change works before claiming done. |
| `apex:pr-discipline` | PR workflow discipline (draft-default, squash-to-one, ≤400 LOC, single-PR review scope). |
| `apex:pr-review-primer` | Copy-paste reviewer-facing description template. |
| `apex:copilot-review-loop` | Copilot bot review loop via GraphQL `requestReviews` mutation; stops at NITs-only OR 5 rounds. |
| `apex:responding-to-review` | PR review-comment discipline — every blocker needs a concrete artifact. |
| `apex:protocol-first-workflow` | Python Protocol-first TDD with mock-count limits. |
| `apex:polymorphic-type-modeling` | Discriminated-union + dispatcher + wire-format-symmetry rules for new variants. |
| `apex:verify-ports` | 5-point checklist when copying code from another repo. |
| `apex:summarize-changes` | Branch / working-tree summary with risks and likely verification commands. |
| `apex:memory-note` | Capture a high-signal lesson or durable project fact to memory. |

### Hooks

| Hook | Event | Behavior |
|---|---|---|
| `suggest-skill-on-prompt` | UserPromptSubmit | Injects review-skill reminders on Python / TS / API surface keywords |
| `suggest-skill-on-edit` | PreToolUse (Edit/Write/MultiEdit) | Reminds to invoke `api-surface-review` on API-surface paths |
| `guard-security-paths` | PreToolUse (Edit/Write/MultiEdit) | Security-review reminder on auth / credentials / oauth / secrets paths |
| `guard-dependency-bump` | PreToolUse (Edit/Write/MultiEdit) | Review-risk reminder on dependency manifests and lock files |
| `guard-destructive` | PreToolUse (Bash) | Blocks `rm -rf` on root/home, force-push to main, `--no-verify` commits, `.env` writes |
| `scan-secrets-on-edit` | PreToolUse (Edit/Write/MultiEdit) | **Blocks** writes containing real-shaped secrets (AWS / GitHub PAT / Stripe / Slack / Anthropic / OpenAI / Google / SSH keys) |
| `format-on-save` | PostToolUse (Edit/Write/MultiEdit) | Auto-formats `.py` (ruff), `.ts/.tsx/.js/.json/.md/.yaml/.css` (prettier) |
