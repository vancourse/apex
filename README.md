# apex

An opinionated Claude Code plugin that bundles a personal SDLC framework — planning gates, code-review skills, PR workflow discipline, and workflow-automation hooks. Designed to make AI-assisted coding survive a strict reviewer.

**New to apex?** Start with **[HOWTO.md](HOWTO.md)** for install + the 6-command quickstart, then **[WALKTHROUGH.md](WALKTHROUGH.md)** for the idea → shipped product/feature path in order. **See [FLOW.md](FLOW.md)** for the phase-by-phase flowchart and skill × phase matrix.

**Already using a spec-driven tool?** apex composes with [GitHub Spec Kit](https://github.com/github/spec-kit) and [BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) — author specs with them, then run apex's adversarial review/freeze gates on their artifacts. See **[INTEROP.md](INTEROP.md)**.

**Contributing to apex itself?** See **[MAINTAINING.md](MAINTAINING.md)** for maintainer-only discipline (pair-pattern verification, slash-menu-count grep, etc.). The PreToolUse hook surfaces it automatically when you edit `skills/`, `commands/`, `hooks/`, or `rules/` inside the apex plugin repo.

## What's in the box

### Skills

For *when* each skill fires, see [FLOW.md](FLOW.md). This table is what each skill *does*.

| Skill | What it does |
|---|---|
| `architecture-design` | **7-pass foundational architecture review** (framework / persistence + tenancy / trust boundaries + auth + data classification / observability + deploy / design system / branch + release / system-level STRIDE threat model). Each pass outputs an ADR. Architecture FREEZES after all 7 ADRs are accepted. One-time at project start; re-runs only on amendment-triggering changes. |
| `adr-review` | Review a single Architecture Decision Record. 5-element audit — context, decision, alternatives (≥2 real), consequences (incl. security + reversibility), status field. Fires for every ADR (initial set + amendments). |
| `prd-review` | **7-pass PRD audit** (acceptance criteria / **testable scenarios enumerated — each tagged by highest test layer (integration / E2E); compound ones optionally broken into use-case one-liners** / out-of-scope / unknowns / success metric / sequencing / **spec-freeze readiness**) + internal-product-overlap scan + OSS-alternatives scan + inline adversarial counter-pass. The SPEC-phase gate, before design. |
| `apex-flow` | Umbrella planning gates: §1a reconnaissance + §1b adversarial design checklist + §1c verify ask vs raw quotes + phase-routing pointer |
| `recon` | **Reconnaissance brief before design** — promotes `apex-flow` §1a from an in-head checklist into a first-class artifact. Scoped to the change's blast radius: enumerate the authoritative primitives that already answer the design's questions, distill their **contracts (not signatures)**, capture invariants + trust boundaries, run the producer/consumer + first-affordance checks against that fact base, and persist durable semantic facts to `domain-knowledge`. Emits a short **Recon Brief** that `design-feature` / §1b consume. Auto-nudged by `suggest-skill-on-prompt` on subtractive-design traps ("shrink/bloated X", "support a new scope/kind/variant"). |
| `design-feature` | Feature-design-from-scratch gate (NEW features, not fixes) — scenarios + MVP cut + deferral list + integration with existing surface + failure modes + **§6 attack surface (invokes apex:threat-model)**, with product-overlap + OSS-alternatives + adversarial counter-pass. Distinct from `apex-flow` §1b which is generic. |
| `threat-model` | Per-feature STRIDE threat model at design time — Spoofing / Tampering / Repudiation / Information disclosure / Denial of service / Elevation of privilege, against the feature's attack surface anchored on `architecture-design` Passes 3 + 7. Outputs a "Threat Model" section appended to the design doc that `security-review` audits at PR time. |
| `observability-review` | **Per-feature design-phase observability-contract gate (5 passes)** — structured logging (one log per failure *decision*, correlation-tagged) / metrics + cardinality budget (each feeds a named SLI) / tracing + causality across sync + async boundaries / alerting + SLO (page on *symptoms* not causes, runbook + owner) / privacy in telemetry (no PII/secrets in logs, metrics, traces). Asks *"when this misbehaves in prod, can an operator SEE why?"* Instantiates the stack + SLO/alerting policy from `architecture-design` Pass 4 per-feature; distinct from `security-review` Pass 5 (security-event slice at PR time). Outputs an "Observability" section the design doc carries. Plus adversarial counter-pass. |
| `design-review` | **6-pass adversarial re-pass + design-freeze ceremony** for a design produced by `design-feature` — re-walks scenarios / MVP cut / deferral list / integration / failure modes / attack surface from the *attack* lens, run cold in a separate cognitive step so the steelman author voice and the attack review voice don't blur. Adds explicit design-freeze (the gate between "design drafted" and "impl plan may begin"). The author/review split for the design phase, mirroring PRD, ADR, and impl-plan. 2-agent cooperative+adversarial pair is the default for non-trivial designs. |
| `impl-plan-review` | 5-pass review of the implementation plan (how to BUILD it, not what to build) — layered PR stack + sequencing + test plan per layer (PRD scenarios/use-cases → tests 1:1; each layer names the scenario(s) it serves; E2E-tagged scenarios get a Playwright spine owner) + rollout strategy + reversibility. Plus adversarial counter-pass + plan-freeze readiness gate. |
| `adversarial-pair` | **Canonical dispatch mechanic** for running any apex review skill (design, plan, implementation, PR) as two parallel worktree-isolated agents — cooperative steelman + adversarial attacker — and reconciling findings. Pointed to by `prd-review`, `design-feature`, `design-review`, `impl-plan-review`, `threat-model`, `adr-review`, `architecture-design`, `observability-review`, `data-migration-review`, `security-review`. Removes apex's prior runtime dependency on `superpowers:dispatching-parallel-agents` — apex stands alone for review-shaped two-voice work. |
| `spec-view` | Renders a frozen (or freeze-candidate) PRD / ADR set / design doc as a **disposable, fully-offline rich-HTML view** for human freeze-review — color-coded freeze-readiness dashboard, inline-SVG data-flow / STRIDE / MVP-vs-deferred diagrams, collapsible review passes, severity badges, syntax-highlighted code. The Markdown stays canonical; the HTML is a throwaway view written to `tmp/apex-views/` (gitignored, never re-ingested by downstream skills). A human-judgment aid at the freeze gates, not a substitute for `prd-review` / `adr-review` / `design-review`. |
| `test-strategy` | The methodology layer for HOW to test — 8-layer model (Unit / Service-real-DB / Router-contract / Backend-scenario / FE-component / Spine-E2E / Visual-E2E / Drift) + mocking policy per layer + CI tiering (PR / 4h / nightly / weekly drift) + isolation patterns (transaction rollback, per-test runtime budget) + pre-seeded data (static / golden / per-test) + recorded fixtures (VCR-style) + anti-goals + 17 language-agnostic test design rules. Language-specific tooling lives in `python-review/rules/testing.md` and `typescript-review/rules/testing.md`. |
| `test-coverage-audit` | Pre-PR audit (5 passes) — PRD↔test mirror (1:1 integration + E2E-tag check: E2E-tagged scenarios need a real Playwright test; + each use-case → ≥1 named assertion), layer discipline, CI tier discipline, mock budget, failure-mode coverage. Distinct from `ai-pre-review-checklist` Step 6 (which audits test QUALITY); this audits test COVERAGE and architecture. |
| `cross-artifact-consistency` | **Read-only HORIZONTAL consistency check** across a feature's frozen PRD ↔ design ↔ impl-plan — builds a traceability matrix (scenarios/use-cases → design elements → layers) and flags **DROPPED** scenarios, **ORPHAN** elements/layers, and **CONFLICT**s (cited), routing each to the upstream gate to re-open. Distinct from the *vertical* `prd-review`/`design-review`/`impl-plan-review` (each audits one artifact); this checks they still **agree**. Reuses `test-coverage-audit` Pass 1's enumeration one hop upstream. Read-only + ephemeral; fires at the impl-plan-freeze boundary / on demand. |
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
| `data-migration-review` | **5-pass DESIGN-PHASE data-safety gate** for MOVING / TRANSFORMING data that already exists (backfills, bulk updates, re-types, relocations, data-model migrations over populated tables) — expand→migrate→contract *at the data level* / backfill design (batched + idempotent + resumable + throttled + observable) / consistency model + reconciliation during the window / mid-flight reversibility / blast radius + isolation + kill-switch. Plus adversarial counter-pass. Audits *will this backfill corrupt, lose, or leak data, and can we stop it halfway* — distinct from `impl-plan-review` Pass 4 (rollout sequencing) and `postgres-review` (schema DDL). Outputs a "Data Migration Plan" section the impl-plan carries. |
| `summarize-changes` | Branch / working-tree summary with risks and likely verification commands |
| `memory-note` | Capture a high-signal lesson or durable project fact to memory/domain-knowledge |
| `incident-retro` | **Post-release learning loop** — take a *resolved* production incident (or staging near-miss), run a blameless retro, map it to the apex gate that **should have caught it** (reads `FLOW.md`), write the durable lesson to `domain-knowledge` via `memory-note`, and propose a one-line preventative gate amendment. The *learning* half of a postmortem only — **not** incident response (no paging / sev / timelines). User-invoked, zero ambient cost. |
| `autonomous-fix` | **Unattended/supervised bug-fix gate** — the discipline a label/webhook/cron-triggered coding agent MUST satisfy before raising a bug-fix PR: five rail phases via a two-invocation runner split (budget+risk-route → read-only investigate → reproduce-first → sensitive-path refuse+escalate → constrained write fix → DRAFT PR), in two modes differing by **only** the human-confirm step. Ships ONE commented GH-Actions reference template (wraps any runner) + a static conformance-lint + a "port these seams" list. Nonce-fenced untrusted input incl. title · default-deny tool allowlist with staged write-unlock · turn/timeout/concurrency/**fail-closed cost** budgets · secret/customer-data leak hard-fail · **draft-PR only (human merges, permanent)**. Composes `systematic-debugging` + `security-review`/`threat-model` + `pr-discipline` + `incident-retro`. The generic parent of a project's bug-bot; ships the rails, NOT a runner. |

**Side paths (apex defers; install separately):** `superpowers:systematic-debugging` for debug discipline, and `superpowers:test-driven-development` for the red-green loop (write the failing test first) that `test-strategy` assumes — apex owns scenario sourcing + layer placement + mock budget *around* that loop but does not re-implement it. The two-agent cooperative+adversarial pair pattern referenced by `prd-review`, `design-feature`, `design-review`, and `impl-plan-review` (the default for non-trivial designs / impl plans) is now owned by apex via **`apex:adversarial-pair`** — `superpowers:dispatching-parallel-agents` is the generic external alternative but apex stands alone.

### Commands

The slash menu is intentionally small: **only the entry-point commands you actually type appear there.** apex's review gates fire *automatically* (driven by their skill `description` + the `suggest-skill-*` hooks, based on phase + file paths), so they are **skills, not slash commands** — keeping the `/apex:` menu focused on the ~14 things you drive by hand instead of burying them under 30+ auto-fired gates. (To run an auto gate by hand, just ask — e.g. "run security-review on this diff"; the model invokes the skill by name.)

> Command names are short; the skill they invoke may differ (e.g. `/apex:design` runs the `design-feature` skill, `/apex:flow` runs `apex-flow`). The Skills table above lists skills by their internal name.

| Command | Backing skill | What it does |
|---|---|---|
| `/apex:flow` | `apex-flow` | Catch-all router — loads the planning gates (reconnaissance + adversarial checklist) and points at `FLOW.md`. Type this when unsure which gate you're at. |
| `/apex:prd` | *(orchestrator)* | Author a new PRD — chains `superpowers:brainstorming` (explore intent) → `superpowers:writing-plans` (draft the spec). The `prd-review` skill then fires to audit + freeze. |
| `/apex:arch` | `architecture-design` | 7-pass foundational architecture review (one-time at project start). The `adr-review` skill fires per ADR. |
| `/apex:recon` | `recon` | Reconnaissance brief before design — surface the existing primitives, contracts, and invariants in the change's blast radius and emit a facts brief, so the design uses what already exists. Also auto-nudged by the `suggest-skill-on-prompt` hook on subtractive-design traps. |
| `/apex:design` | `design-feature` | Feature-design-from-scratch gate. The `design-review` skill then fires for the adversarial re-pass + freeze. |
| `/apex:impl-plan` | *(orchestrator)* | Author an implementation plan against the frozen design — chains `superpowers:writing-plans`. The `impl-plan-review` skill then fires. |
| `/apex:review-pr` | *(orchestrator)* | Heavy multi-agent pre-PR review — dispatches 6 cooperating specialist agents (`code-reviewer`, `comment-analyzer`, `pr-test-analyzer`, `silent-failure-hunter`, `type-design-analyzer`, `code-simplifier`) from the `pr-review-toolkit` plugin in parallel. Optional, for non-trivial branches. |
| `/apex:copilot-review` | `copilot-review-loop` | Trigger + iterate the Copilot bot review on an open PR. |
| `/apex:spec-view` | `spec-view` | Renders a PRD / ADR set / design doc as a disposable offline rich-HTML view for human freeze-review. |
| `/apex:test` | `test-strategy` | Focuses `test-strategy` on one layer — maps an industry term (`unit` / `integration` / `smoke` / `e2e` / `component` / `visual` / `drift`) or an apex layer name to the 8-layer model, then surfaces what to test there, what to mock, and which CI tier. Advisory router; **does not run the suite**. No argument → the 8-layer menu. |
| `/apex:remember` | `memory-note` | Capture a high-signal lesson or durable project fact to memory. |
| `/apex:help` | *(orchestrator)* | Prints the cheat sheet — which commands you type vs. which skills fire automatically, plus the SDLC workflow at a glance. |
| `/apex:setup` | *(orchestrator)* | Guided installer for apex's companions (`superpowers`, `pr-review-toolkit`, `frontend-design`), an optional large-codebase context tool (Graphify / Serena / Claude Context), and optional gastown-ecosystem tooling (beads `bd` + gastown `gt`) — asks what you want, then **installs for real via the `claude` CLI** (falls back to printing `/plugin` commands when the CLI isn't available). |

Everything else listed in the Skills table above is a **skill that fires automatically** at its phase — `prd-review`, `adr-review`, `design-review`, `impl-plan-review`, the language/`api-surface`/`postgres` reviews, `security-review`, `threat-model`, `pr-discipline`, and the rest. They have no slash command by design; the model invokes them, and you can ask for any of them by name.

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
| `suggest-review-on-stop.sh` | Stop | Soft-blocks the assistant's stop attempt once per session when ≥20 LOC of uncommitted code edits (tracked diff + untracked new files) touch `.py` / `.ts` / `.tsx` — nudges the agent to invoke `apex:python-review` / `apex:typescript-review` before declaring done |

### Rules

Reference files at `rules/`, loaded on-demand by skills:

- `rules/principles.md` — **canonical** cross-cutting design principles (producer/consumer dual, first-plausible-affordance, pure-addition smell, wire-format symmetry, SR primitives). Multiple skills apply these in their own context; the principle itself is stated here once.
- `rules/responding-to-review.md` — **canonical** PR-review-comment protocol (blocker artifact rule, reply structure, mechanical flagged-line verification, pre-re-review gate).
- `rules/frontend.md` — design-system reuse, focus states, empty/loading/error states, no hardcoded tokens
- `rules/review-risk.md` — pre-merge checklist for auth/data/concurrency/billing/external-API touch points

These are not auto-loaded. Skills reference them by anchor; your own CLAUDE.md can reference them when relevant.

### Recommended companions (install separately)

These are not declared as `dependencies` in `plugin.json` — Claude Code's dependency resolver requires every listed dep to resolve to an installable plugin by name, and a single typo or a name that's actually a skill (rather than a plugin) silently fails the entire install. We keep apex's manifest dependency-free and list its useful companions here instead:

- `superpowers` (in `obra/superpowers` marketplace) — brainstorming, planning, debugging, TDD skills; backs `/apex:prd`, `/apex:impl-plan`, and the TDD red-green loop (the 2-agent adversarial pair is owned by apex via `apex:adversarial-pair`, no superpowers dependency)
- `pr-review-toolkit` — the 6 cooperating specialist agents `/apex:review-pr` dispatches
- `frontend-design` (in `anthropics/claude-plugins-official`) — distinctive, polished frontend interfaces
- `skill-creator` (in `anthropics/claude-plugins-official`) — create / iterate skills
- `anthropic-skills` (in `anthropics/claude-plugins-official`) — bundles `consolidate-memory`, `pdf`, `xlsx`, `docx`, `pptx`, `skill-creator`, and others

Install each separately via `/plugin install <name>@<marketplace>`, or run **`/apex:setup`** — a guided installer that detects your environment, asks which companions you want, and **installs them for real** via the `claude` CLI (`claude plugin install … --scope user`), falling back to printing the exact `/plugin` commands when the CLI isn't on PATH.

> **Licensing:** apex **bundles none of these** — the companions and the large-codebase context tools below are independent, third-party projects, each under its own license, installed directly from their own sources. apex only *references* them by name and recommends them; nothing here is redistributed as part of apex (which is MIT — see [LICENSE](LICENSE)). Review each tool's license before use.

## Large-codebase context tools (optional)

On a big repo, Claude re-reads/greps the tree every session. A structural index fixes that — apex's `recon` (Step 1) and everyday navigation query the index instead of sweeping blind. These are third-party tools, not apex skills; `/apex:setup` will walk you through one. Pick **one** that matches how you work:

| Tool | Approach | Best for | Note |
|---|---|---|---|
| **[Graphify](https://github.com/safishamsi/graphify)** | Committed knowledge graph (tree-sitter AST, 33 langs) + a PreToolUse hook so Claude consults it *before* file-search | "Map it once, reuse every session"; team-shared via git | Local extraction. `uv tool install graphifyy && graphify install`, then `/graphify .` |
| **[Serena](https://github.com/oraios/serena)** | Live LSP symbol navigation + safe symbol-level edits | Always-fresh navigation with **no index to maintain** (never stale) | MCP server; symbolic, not RAG |
| **[Claude Context](https://github.com/zilliztech/claude-context)** | Semantic vector search (hybrid embeddings + BM25) | "Find the code about X" across millions of LOC | MCP server; needs a Milvus/Zilliz vector DB |

**The staleness rule (matches `recon`):** a committed/cached structural index is a fast *navigation aid, not ground truth* — it answers *where code lives*, not *what it guarantees*. Always read the actual function for its contract (recon Step 2). **Presence is not freshness:** a confidently-stale index is *worse* than none, because it reads as authoritative while pointing at moved or deleted primitives — so when the index is absent or possibly stale, recon caveats the Brief rather than implying full coverage. Division of labor: **apex queries the index; the tool maintains it** (Graphify's post-commit hook auto-rebuilds; Serena is live by construction; Claude Context re-indexes). This mirrors apex's split: **structural facts are ephemeral; semantic facts are durable** (persist those via `/apex:remember`).

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

## Optional: the `apex-terse` output style

apex's gates are deliberately verbose where it matters — but the *conversational
prose around* a gate (preamble, transitions, restating the task, post-hoc
summaries) carries no review signal and still costs tokens. The `apex-terse`
output style cuts that wrapper **without** dulling the gate.

It is **scoped**, not a blanket "be brief" instruction. It exempts apex's
load-bearing zones — the adversarial counter-passes, per-finding `file:line`
evidence, and freeze-decision rationale — which expand to whatever the argument
needs. A terse adversarial counter-pass would collapse a *review* back into a
*checklist* (the exact failure mode apex exists to prevent), so those stay
full-fidelity. The savings come only from words that carry no review signal.

Output styles are a Claude Code user-level setting; a plugin can't ship one as
active context, so install it by copying the file:

```bash
# from a clone of this repo:
mkdir -p ~/.claude/output-styles
cp output-styles/apex-terse.md ~/.claude/output-styles/
```

Then switch to it with `/output-style apex-terse` (and back with
`/output-style default`). It composes with the skill gates — flip it on for a
token-lean session; the gates keep their full fidelity.

## Install

```bash
claude /plugin install github:vancourse/apex
```

Restart Claude Code after installing. The skills and hooks activate immediately in the next session.

### Install by asking Claude (paste-to-install)

Prefer to let Claude do the work? Paste the block below into any Claude Code session and Claude will run the install for you. apex is public (MIT) — no GitHub auth or org membership required.

```text
Please install the apex Claude Code plugin from https://github.com/vancourse/apex — an opinionated SDLC framework: planning gates, adversarial review skills, PR workflow discipline, and workflow-automation hooks.

Run these in order, and stop and ask me if any step fails:
1. `claude plugin marketplace add vancourse/apex` — register the marketplace. If it says it already exists, that's fine, continue.
2. `claude plugin install apex@apex` — install the plugin. If it's already installed, run `claude plugin update apex@apex` instead.
3. `claude plugin list | grep apex` — show me the output so I can confirm.

When done, remind me to start a NEW Claude Code session (slash commands only register at session start) and type `/apex:help` — I should see the 14-command cheat sheet (`/apex:flow`, `/apex:prd`, `/apex:design`, `/apex:impl-plan`, `/apex:adversarial-pair`, …). Optionally, run `/apex:setup` to install the recommended companion plugins.
```

### Quickstart

After installing, add the skill-gate stubs from the "Suggested additions" section above to your `~/.claude/CLAUDE.md`. Then try your first skill — e.g. before starting any non-trivial change:

```
/apex:flow
```

> **Note:** The CLAUDE.md stubs above use short names like `apex-flow` and `python-review` (the model's routing name). Only the 14 **entry-point** commands have an interactive `/apex:` slash form (e.g. `/apex:flow`); the review gates below are **skills** the model fires automatically — they are not in the slash menu.

The entry-point commands you type:

| When you're... | Type |
|---|---|
| Starting any non-trivial change (unsure which gate) | `/apex:flow` |
| Authoring a PRD | `/apex:prd` |
| Setting up architecture (once, at project start) | `/apex:arch` |
| Reconnaissance before designing (esp. "shrink X" / "support new X") | `/apex:recon` |
| Designing a feature | `/apex:design` |
| Writing the implementation plan | `/apex:impl-plan` |
| Doing a heavy pre-PR review | `/apex:review-pr` |
| Iterating the Copilot review on a PR | `/apex:copilot-review` |

Everything else fires automatically by phase + file path — write Python and `python-review` fires; touch a `routes/` file and `api-surface-review` fires; reach the PR phase and `security-review` / `pr-discipline` fire. You don't type those. See [FLOW.md](FLOW.md) for the full phase-by-phase routing map.

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
