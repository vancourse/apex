# apex

An opinionated Claude Code plugin that bundles a personal SDLC framework — planning gates, code-review skills, PR workflow discipline, and workflow-automation hooks. Designed to make AI-assisted coding survive a strict reviewer.

**New to apex?** Start with **[WALKTHROUGH.md](WALKTHROUGH.md)** — the idea → shipped product/feature path in order (which ~6 commands you type, which gates fire automatically, where to freeze). **See [FLOW.md](FLOW.md)** for the phase-by-phase flowchart and skill × phase matrix.

## What's in the box

### Skills

For *when* each skill fires, see [FLOW.md](FLOW.md). This table is what each skill *does*.

| Skill | What it does |
|---|---|
| `architecture-design` | **7-pass foundational architecture review** (framework / persistence + tenancy / trust boundaries + auth + data classification / observability + deploy / design system / branch + release / system-level STRIDE threat model). Each pass outputs an ADR. Architecture FREEZES after all 7 ADRs are accepted. One-time at project start; re-runs only on amendment-triggering changes. |
| `adr-review` | Review a single Architecture Decision Record. 5-element audit — context, decision, alternatives (≥2 real), consequences (incl. security + reversibility), status field. Fires for every ADR (initial set + amendments). |
| `prd-review` | **7-pass PRD audit** (acceptance criteria / **testable scenarios enumerated** / out-of-scope / unknowns / success metric / sequencing / **spec-freeze readiness**) + internal-product-overlap scan + OSS-alternatives scan + inline adversarial counter-pass. The SPEC-phase gate, before design. |
| `apex-flow` | Umbrella planning gates: §1a reconnaissance + §1b adversarial design checklist + §1c verify ask vs raw quotes + phase-routing pointer |
| `design-feature` | Feature-design-from-scratch gate (NEW features, not fixes) — scenarios + MVP cut + deferral list + integration with existing surface + failure modes + **§6 attack surface (invokes apex:threat-model)**, with product-overlap + OSS-alternatives + adversarial counter-pass. Distinct from `apex-flow` §1b which is generic. |
| `threat-model` | Per-feature STRIDE threat model at design time — Spoofing / Tampering / Repudiation / Information disclosure / Denial of service / Elevation of privilege, against the feature's attack surface anchored on `architecture-design` Passes 3 + 7. Outputs a "Threat Model" section appended to the design doc that `security-review` audits at PR time. |
| `design-review` | **6-pass adversarial re-pass + design-freeze ceremony** for a design produced by `design-feature` — re-walks scenarios / MVP cut / deferral list / integration / failure modes / attack surface from the *attack* lens, run cold in a separate cognitive step so the steelman author voice and the attack review voice don't blur. Adds explicit design-freeze (the gate between "design drafted" and "impl plan may begin"). The author/review split for the design phase, mirroring PRD, ADR, and impl-plan. 2-agent cooperative+adversarial pair is the default for non-trivial designs. |
| `impl-plan-review` | 5-pass review of the implementation plan (how to BUILD it, not what to build) — layered PR stack + sequencing + test plan per layer (PRD scenarios → integration tests 1:1) + rollout strategy + reversibility. Plus adversarial counter-pass + plan-freeze readiness gate. |
| `spec-view` | Renders a frozen (or freeze-candidate) PRD / ADR set / design doc as a **disposable, fully-offline rich-HTML view** for human freeze-review — color-coded freeze-readiness dashboard, inline-SVG data-flow / STRIDE / MVP-vs-deferred diagrams, collapsible review passes, severity badges, syntax-highlighted code. The Markdown stays canonical; the HTML is a throwaway view written to `tmp/apex-views/` (gitignored, never re-ingested by downstream skills). A human-judgment aid at the freeze gates, not a substitute for `prd-review` / `adr-review` / `design-review`. |
| `test-strategy` | The methodology layer for HOW to test — 8-layer model (Unit / Service-real-DB / Router-contract / Backend-scenario / FE-component / Spine-E2E / Visual-E2E / Drift) + mocking policy per layer + CI tiering (PR / 4h / nightly / weekly drift) + isolation patterns (transaction rollback, per-test runtime budget) + pre-seeded data (static / golden / per-test) + recorded fixtures (VCR-style) + anti-goals + 17 language-agnostic test design rules. Language-specific tooling lives in `python-review/rules/testing.md` and `typescript-review/rules/testing.md`. |
| `test-coverage-audit` | Pre-PR audit (5 passes) — PRD↔integration test 1:1 mirror, layer discipline, CI tier discipline, mock budget, failure-mode coverage. Distinct from `ai-pre-review-checklist` Step 6 (which audits test QUALITY); this audits test COVERAGE and architecture. |
| `security-review` | **PR-time security audit (5 passes)** — secrets management, authentication + authorization (per-layer + fail-closed), input validation + output encoding, dependency vulnerability + supply-chain integrity, audit log + observability for security events. Verifies implementation against the feature's threat model output. Plus adversarial counter-pass. |
| `pr-discipline` | Draft-PR default, pre-commit + minimal-push, layered PR stacks (≤400 LOC), single-PR review scope, self-review checklist, responding-to-comments pointer |
| `api-surface-review` | 5-pass review of new endpoints / payloads / handlers from the *consumer's* perspective |
| `ai-pre-review-checklist` | 9-step robustness gate for AI-assisted branches (branch explanation, layering, state, concurrency, fallback, tests, **consumer-tracing**, reviewer sim, gaps) |
| `verification-before-completion` | Phase 3 gate — prove the change works before claiming done (run tests, check logs, exercise in browser, cover edge cases) |
| `verify-ports` | 5-point checklist when copying code from another repo (schema / product state / UX / external format / defensive code) |
| `responding-to-review` | PR review-comment discipline — every blocker needs a concrete artifact, every reply maps to a diff |
| `copilot-review-loop` | PR review loop with the Copilot bot reviewer — GraphQL `requestReviews` mutation (REST + `gh` CLI silently no-op on bots), GraphQL verification, request → wait → address → re-request cycle, stop at NITs-only OR 5 rounds whichever first |
| `pr-review-primer` | Copy-paste reviewer-facing description template |
| `polymorphic-type-modeling` | Discriminated-union + dispatcher + wire-format-symmetry rules for new variants |
| `protocol-first-workflow` | Python Protocol-first TDD with mock-count limits and stub generation |
| `python-review` | Generic cross-project Python rules with a routing table to 11 topic files |
| `typescript-review` | Generic TS/React rules with a routing table to 13 topic files |
| `postgres-review` | Generic PostgreSQL review rules — schema design, indexing, migrations, transactions + locking, observability. Routing table inside. Multi-tenant isolation has its own skill: `multi-tenancy`. |
| `multi-tenancy` | Multi-tenant isolation strategies and per-strategy review rules — Postgres RLS today; schema-per-tenant, DB-per-tenant, app-layer filtering, tenant-context propagation, tenant-data-export, billing-aware isolation planned. For the *strategy-choice* (which model to use) see `architecture-design` Pass 2; this skill is the per-strategy detail. |
| `summarize-changes` | Branch / working-tree summary with risks and likely verification commands |
| `memory-note` | Capture a high-signal lesson or durable project fact to memory/domain-knowledge |

**Side paths (apex defers; install separately):** `superpowers:systematic-debugging` for debug discipline, `superpowers:dispatching-parallel-agents` for the two-agent cooperative+adversarial pair pattern referenced by `prd-review`, `design-feature`, `design-review`, and `impl-plan-review` (the default for non-trivial designs / impl plans), and `superpowers:test-driven-development` for the red-green loop (write the failing test first) that `test-strategy` assumes — apex owns scenario sourcing + layer placement + mock budget *around* that loop but does not re-implement it.

### Commands

Slash commands are thin entry points. Most map 1:1 to a skill of the same name; the orchestration commands below chain several skills (and, for two of them, agents from companion plugins). Every command's `description` carries a **`[USER]`** or **`[AUTO]`** tag so the slash menu signals whether *you* type it at a phase boundary or the model fires it automatically based on phase + file paths.

| Command | Tag | What it does |
|---|---|---|
| `/apex:create-prd` | `[USER]` | Author a new PRD — chains `superpowers:brainstorming` (explore intent) → `superpowers:writing-plans` (draft the spec). Suggests `/apex:prd-review` afterward to audit + freeze. |
| `/apex:create-impl-plan` | `[USER]` | Author an implementation plan against the frozen design — chains `superpowers:writing-plans`. Suggests `/apex:impl-plan-review` afterward. |
| `/apex:design-review` | `[AUTO]` | Backs the `design-review` skill — the adversarial re-pass + freeze ceremony for the design phase. |
| `/apex:spec-view` | `[USER]` | Backs the `spec-view` skill — renders a PRD / ADR set / design doc as a disposable offline rich-HTML view for human freeze-review. |
| `/apex:review-pr` | `[USER]` | Heavy multi-agent pre-PR review — dispatches 6 cooperating specialist agents (`code-reviewer`, `comment-analyzer`, `pr-test-analyzer`, `silent-failure-hunter`, `type-design-analyzer`, `code-simplifier`) from the `pr-review-toolkit` plugin in parallel. Optional, for non-trivial branches. |
| `/apex:help` | `[USER]` | Prints the command cheat sheet — which commands you type vs. which the model fires automatically, plus the SDLC workflow at a glance. |
| `/apex:test` | `[USER]` | Focuses `test-strategy` on one layer — maps an industry term (`unit` / `integration` / `smoke` / `e2e` / `component` / `visual` / `drift`) or an apex layer name to the 8-layer model, then surfaces what to test there, what to mock, and which CI tier. Advisory router; **does not run the suite** (the runner is project-specific). No argument → the 8-layer menu. |

`design-review` and `spec-view` are full skills (see the Skills table); the other five are command-only orchestrators/routers with no standalone skill body (`/apex:test` routes to the `test-strategy` skill). All remaining skills are also invocable as `/apex:<skill-name>`.

### Hooks

| Hook | Event | Behavior |
|---|---|---|
| `suggest-skill-on-prompt.sh` | UserPromptSubmit | Injects review-skill reminders when the prompt mentions Python / TS / API surface keywords |
| `suggest-skill-on-edit.sh` | PreToolUse (Edit/Write/MultiEdit) | Reminds you to invoke `api-surface-review` when editing files under `payloads/`, `routes/`, `services/`, `handlers/`, `endpoints/`, `api/` |
| `guard-security-paths.sh` | PreToolUse (Edit/Write/MultiEdit) | Injects security-review reminder on edits to `auth/`, `credentials/`, `oauth/`, `oidc/`, `sso/`, `secrets/`, `jwt/`, `saml/`, `encryption/`, `signing/`, `permissions/`, `authorization/` paths |
| `guard-dependency-bump.sh` | PreToolUse (Edit/Write/MultiEdit) | Injects review-risk reminder on edits to `package*.json`, `*-lock.{yaml,json}`, `*.lock`, `pyproject.toml`, `Cargo.{toml,lock}`, `go.{mod,sum}`, `Gemfile*`, `composer.*` |
| `guard-destructive.sh` | PreToolUse (Bash) | Blocks `rm -rf` on root/home/parent, force-push to main, `--no-verify` commits, `.env` writes, `git reset --hard origin` |
| `scan-secrets-on-edit.sh` | PreToolUse (Edit/Write/MultiEdit) | **BLOCKS** writes containing real-shaped secrets (AWS / GitHub PAT / Stripe / Slack / Anthropic / OpenAI / Google API keys; SSH/RSA private key blocks). Exempts test fixtures marked with `FAKE`/`EXAMPLE`/`TEST`/`DUMMY`/`FIXTURE`/`REPLACE`/`YOUR_` |
| `format-on-save.sh` | PostToolUse (Edit/Write/MultiEdit) | Auto-formats `.py` (ruff), `.ts/.tsx/.js/.json/.md/.yaml/.css` (prettier — project-local first, then global) |

### Rules

Reference files at `rules/`, loaded on-demand by skills:

- `rules/principles.md` — **canonical** cross-cutting design principles (producer/consumer dual, first-plausible-affordance, pure-addition smell, wire-format symmetry, SR primitives). Multiple skills apply these in their own context; the principle itself is stated here once.
- `rules/responding-to-review.md` — **canonical** PR-review-comment protocol (blocker artifact rule, reply structure, mechanical flagged-line verification, pre-re-review gate).
- `rules/frontend.md` — design-system reuse, focus states, empty/loading/error states, no hardcoded tokens
- `rules/review-risk.md` — pre-merge checklist for auth/data/concurrency/billing/external-API touch points

These are not auto-loaded. Skills reference them by anchor; your own CLAUDE.md can reference them when relevant.

### Recommended companions (install separately)

These are not declared as `dependencies` in `plugin.json` — Claude Code's dependency resolver requires every listed dep to resolve to an installable plugin by name, and a single typo or a name that's actually a skill (rather than a plugin) silently fails the entire install. We keep apex's manifest dependency-free and list its useful companions here instead:

- `superpowers` (in `obra/superpowers` marketplace) — brainstorming, planning, debugging, TDD, parallel-agent skills
- `frontend-design` (in `anthropics/claude-plugins-official`) — distinctive, polished frontend interfaces
- `skill-creator` (in `anthropics/claude-plugins-official`) — create / iterate skills
- `anthropic-skills` (in `anthropics/claude-plugins-official`) — bundles `consolidate-memory`, `pdf`, `xlsx`, `docx`, `pptx`, `skill-creator`, and others

Install each separately via `/plugin install <name>@<marketplace>` if you want them.

## What this plugin does NOT ship

Plugins cannot contribute system-prompt-level instructions (a `CLAUDE.md` at the plugin root is intentionally not loaded as context). The methodology lives entirely in skills, hooks, and rule files — there is no ambient ruleset injected on every turn.

Your `~/.claude/CLAUDE.md` is still the right home for personal guidance that must always be in context. See the suggested additions below.

## Suggested additions to `~/.claude/CLAUDE.md`

Paste this into your global `~/.claude/CLAUDE.md` after installing the plugin. The plugin's skills handle the deep content; this stub points the model at them at the right moments.

```markdown
# Personal Rules

## 1. Plan Before Coding

For any non-trivial change, invoke `apex-flow` to load the planning gates
(reconnaissance, adversarial checklist) before writing code.

## 2. Skill Gates

- **Planning / design** that touches an endpoint, payload, or handler →
  invoke `api-surface-review` against the *proposed* shape, before writing code.
- **Implementing** Python → invoke `python-review`.
- **Implementing** TypeScript/React → invoke `typescript-review`.
- **Implementing** a UI change → invoke `frontend-design`.
- **Pre-PR** → invoke `ai-pre-review-checklist` + language-specific review skill.
- **Opening a PR** → invoke `pr-review-primer` for the description.
- **Reviewing a PR** → invoke `pr-discipline` (single-PR scope) + language review skill.

Run skills at every matching phase, not just the first. Invoking `api-surface-review`
during planning does not discharge the implementation gate — design intent and
code reality diverge.

## 3. Prove It Works

A task is never "done" until verified. Run tests, check logs, or use the browser.
Do not declare completion based on code changes alone.

## 4. Domain-Specific Knowledge

Long-lived project-specific facts live in `~/.claude/domain-knowledge/<project>.md`.
Read the relevant file at the start of any session that touches that project.
```

## Install

```bash
claude /plugin install github:vancourse/apex
```

Restart Claude Code after installing. The skills and hooks activate immediately in the next session.

### Quickstart

After installing, add the skill-gate stubs from the "Suggested additions" section above to your `~/.claude/CLAUDE.md`. Then try your first skill — e.g. before starting any non-trivial change:

```
/apex:apex-flow
```

> **Note:** The CLAUDE.md stubs above use short names like `apex-flow` and `python-review` (the model's routing name). The interactive slash command in Claude Code adds the plugin prefix: `/apex:apex-flow`, `/apex:python-review`, etc.

Other common entry points:

| When you're... | Run |
|---|---|
| About to write Python | `/apex:python-review` |
| About to write TypeScript/React | `/apex:typescript-review` |
| Touching a Postgres schema or SQL | `/apex:postgres-review` |
| Touching tenant-scoped tables or RLS | `/apex:multi-tenancy` |
| Pre-PR on an AI-assisted branch | `/apex:ai-pre-review-checklist` |
| Opening a PR | `/apex:pr-discipline` then `/apex:pr-review-primer` |

See [FLOW.md](FLOW.md) for the full phase-by-phase routing map.

### Fork and customize

```bash
# 1. Fork on GitHub: https://github.com/vancourse/apex/fork
# 2. Clone your fork:
git clone https://github.com/<your-username>/apex
# 3. Load from disk for the current session:
claude --plugin-dir ./apex
```

- **Add a skill** — drop `skills/<name>/SKILL.md` (frontmatter + body). Picked up automatically via the `description` field.
- **Add a hook** — write the script in `hooks/`, register it in `hooks/hooks.json`.
- **Add a command alias** — drop `commands/<name>.md`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full PR loop apex uses on itself.

## Contributing

apex eats its own cooking — every change opens a draft PR, runs the Copilot review loop, and squash-merges to `main`. **No direct-to-main pushes.** See [CONTRIBUTING.md](CONTRIBUTING.md) for the full rules.

## Why this plugin exists

AI-assisted coding produces locally coherent code that misses branch-shaping concerns: wrong layer, new abstraction without justification, shared-state bugs hidden by happy-path tests, echo-back response fields, hardcoded timeouts with no measured latency.

This plugin packages the gates that catch those failure modes before a human reviewer has to.
