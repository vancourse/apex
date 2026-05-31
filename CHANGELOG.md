# Changelog

All notable changes to apex are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [0.2.2] — 2026-05-31

### Changed

- **`design-review` is now enforced after `design-feature`, not merely flow-prescribed.** Defense-in-depth so the load-bearing adversarial re-pass actually runs before implementation planning:
  - `skills/design-feature/SKILL.md` gains a **mandatory "next step — `apex:design-review`"** section: a `design-feature` draft is *authored, not frozen*; the inline counter-passes are the cheap (contaminated-voice) version, and `design-review` (the cold, separate adversarial re-pass + freeze ceremony) must run before `create-impl-plan` or coding.
  - `hooks/suggest-skill-on-prompt.sh` gains a **design-freeze-gate** block that, when a prompt signals moving toward implementation planning / building (`impl plan`, `start implementing`, `design is done`, …), reminds that `design-review` must have run and frozen the design first — backstopping the case where the move happens in a later prompt.
  - `commands/create-impl-plan.md` hardens its prerequisite: the design must be **FROZEN via `apex:design-review`**, not just drafted, or it stops.

  No new slash command — `design-review` stays a skill (`[AUTO]`), consistent with `prd-review` / `impl-plan-review`; the menu remains 12 commands.

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
- **Orchestration commands** — `/apex:create-prd` (chains `superpowers:brainstorming` → `writing-plans`), `/apex:create-impl-plan` (chains `superpowers:writing-plans`), and `/apex:review-pr` (dispatches 6 `pr-review-toolkit` specialist agents in parallel).
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
