# apex

An opinionated Claude Code plugin that bundles a personal SDLC framework — planning gates, code-review skills, PR workflow discipline, and workflow-automation hooks. Designed to make AI-assisted coding survive a strict reviewer.

**See [FLOW.md](FLOW.md)** for the phase-by-phase flowchart and skill × phase matrix.

## What's in the box

### Skills

For *when* each skill fires, see [FLOW.md](FLOW.md). This table is what each skill *does*.

| Skill | What it does |
|---|---|
| `prd-review` | **7-pass PRD audit** (acceptance criteria / **testable scenarios enumerated** / out-of-scope / unknowns / success metric / sequencing / **spec-freeze readiness**) + internal-product-overlap scan + OSS-alternatives scan + inline adversarial counter-pass. The SPEC-phase gate, before design. |
| `apex-flow` | Umbrella planning gates: §1a reconnaissance + §1b adversarial design checklist + §1c verify ask vs raw quotes + phase-routing pointer |
| `design-feature` | Feature-design-from-scratch gate (NEW features, not fixes) — scenarios + MVP cut + deferral list + integration with existing surface + failure modes, with product-overlap + OSS-alternatives + adversarial counter-pass. Distinct from `apex-flow` §1b which is generic. |
| `impl-plan-review` | 5-pass review of the implementation plan (how to BUILD it, not what to build) — layered PR stack + sequencing + test plan per layer (PRD scenarios → integration tests 1:1) + rollout strategy + reversibility. Plus adversarial counter-pass + plan-freeze readiness gate. |
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
| `summarize-changes` | Branch / working-tree summary with risks and likely verification commands |
| `memory-note` | Capture a high-signal lesson or durable project fact to memory/domain-knowledge |

**Side paths (apex defers; install separately):** `superpowers:systematic-debugging` for debug discipline, `superpowers:dispatching-parallel-agents` for the two-agent adversarial pair pattern referenced by `prd-review` and `design-feature`.

### Hooks

| Hook | Event | Behavior |
|---|---|---|
| `suggest-skill-on-prompt.sh` | UserPromptSubmit | Injects review-skill reminders when the prompt mentions Python / TS / API surface keywords |
| `suggest-skill-on-edit.sh` | PreToolUse (Edit/Write/MultiEdit) | Reminds you to invoke `api-surface-review` when editing files under `payloads/`, `routes/`, `services/`, `handlers/`, `endpoints/`, `api/` |
| `guard-security-paths.sh` | PreToolUse (Edit/Write/MultiEdit) | Injects security-review reminder on edits to `auth/`, `credentials/`, `oauth/`, `oidc/`, `sso/`, `secrets/`, `jwt/`, `saml/`, `encryption/`, `signing/`, `permissions/`, `authorization/` paths |
| `guard-dependency-bump.sh` | PreToolUse (Edit/Write/MultiEdit) | Injects review-risk reminder on edits to `package*.json`, `*-lock.{yaml,json}`, `*.lock`, `pyproject.toml`, `Cargo.{toml,lock}`, `go.{mod,sum}`, `Gemfile*`, `composer.*` |
| `guard-destructive.sh` | PreToolUse (Bash) | Blocks `rm -rf` on root/home/parent, force-push to main, `--no-verify` commits, `.env` writes, `git reset --hard origin` |
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

### Local development (recommended while iterating)

```bash
claude --plugin-dir /Users/ravi/devenv/apex
```

This loads the plugin from disk for a single session. Edit files, reload Claude Code, see changes.

### Distribute via git

```bash
# In the plugin directory
git init && git add -A && git commit -m "Initial commit"
git remote add origin git@github.com:<you>/apex.git
git push -u origin main
```

Then on any machine:

```bash
claude /plugin install <github-url-or-marketplace-name>
```

## Customizing

- **Add a skill** — drop a new `skills/<name>/SKILL.md` (frontmatter + body). The model picks it up automatically based on the `description` field.
- **Add a hook** — write the script in `hooks/`, then register it in `hooks/hooks.json` under the right event (`UserPromptSubmit`, `PreToolUse`, `PostToolUse`, etc.).
- **Add a dependency** — edit the `dependencies` array in `.claude-plugin/plugin.json`.
- **Strip a dependency** — remove from `dependencies`; users without the corresponding marketplace will install cleanly.

## Why this plugin exists

AI-assisted coding produces locally coherent code that misses branch-shaping concerns: wrong layer, new abstraction without justification, shared-state bugs hidden by happy-path tests, echo-back response fields, hardcoded timeouts with no measured latency.

This plugin packages the gates that catch those failure modes before a human reviewer has to.
