# Changelog

All notable changes to apex are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
| `apex:typescript-review` | Generic TypeScript/React rules with routing table to 13 topic files. |
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
| `suggest-skill-on-edit` | PreToolUse (Edit/Write) | Reminds to invoke `api-surface-review` on API-surface paths |
| `guard-security-paths` | PreToolUse (Edit/Write) | Security-review reminder on auth / credentials / oauth / secrets paths |
| `guard-dependency-bump` | PreToolUse (Edit/Write) | Review-risk reminder on dependency manifests and lock files |
| `guard-destructive` | PreToolUse (Bash) | Blocks `rm -rf` on root/home, force-push to main, `--no-verify` commits, `.env` writes |
| `scan-secrets-on-edit` | PreToolUse (Edit/Write) | **Blocks** writes containing real-shaped secrets (AWS / GitHub PAT / Stripe / Slack / Anthropic / OpenAI / Google / SSH keys) |
| `format-on-save` | PostToolUse (Edit/Write) | Auto-formats `.py` (ruff), `.ts/.tsx/.js/.json/.md/.yaml/.css` (prettier) |
