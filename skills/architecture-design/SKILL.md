---
name: architecture-design
description: Foundational architecture decisions for a NEW project (or major architecture-affecting change to an existing one). 7-pass review of the load-bearing choices that constrain all future feature work — framework/runtime, persistence + tenancy, trust boundaries + auth + data classification, observability + deploy, design system, branch/release strategy, system-level threat model. Each pass produces an ADR (Architecture Decision Record). Plus inline adversarial counter-pass at every step. Pairs with apex:adr-review (single-ADR review) and apex:threat-model (per-feature threat surface that builds on this skill's system-level model). Fires once at project start; re-fires when a feature crosses the architecture boundary and triggers an amendment. Keywords: architecture, foundational design, ADR, tenancy, persistence, auth, trust boundary, observability, deploy model, design system, system-level threat model.
---

# Architecture Design

The gate that fires *before* the first feature's PRD. Sets the load-bearing decisions that every subsequent `apex:prd-review` → `apex:design-feature` → `apex:impl-plan-review` pipeline will run against. Once the architecture is frozen, individual features either fit it or trigger an explicit amendment via `apex:adr-review` — they don't silently reshape it.

## When to invoke

- **At project start**, before any feature PRD is written.
- **When a feature genuinely crosses the existing architecture boundary** — the feature's PRD has a scenario that can't be served by the current persistence model, auth model, deploy shape, or tenancy. `apex:design-feature` Pass 4 (integration with existing surface) is where this normally surfaces.
- **When migrating** — e.g. monolith → service split, Postgres → Aurora, JWT → session, single-tenant → multi-tenant.

Pairs with:

- **`apex:adr-review`** — review a single ADR before locking it in (each pass below produces an ADR; that skill audits it)
- **`apex:threat-model`** — per-feature STRIDE-style modeling. This skill's Pass 7 does threat modeling at the *system* level; the threat-model skill does it at the *feature* level using this skill's trust boundaries as input
- **`apex:design-feature`** Pass 4 (integration with existing surface) — verifies a new feature fits the frozen architecture
- **`apex:prd-review`** — runs *against* the architecture this skill produces; if a PRD scenario can't be served by the architecture, raise the conflict before freezing the spec

## Adversarial counter-pass — read this first

Every pass below has an inline adversarial counter-pass. Architecture decisions are the most expensive to undo — adversarial pressure here pays back the most. For non-trivial architecture work, dispatch the heavier two-agent version via `superpowers:dispatching-parallel-agents`.

## The 7 passes (each outputs one ADR)

### Pass 1 — Framework / runtime / language

**Check:** State the language, runtime, framework, and major libraries. For each, name 2 alternatives considered and why this won.

**Why:** Framework choice cascades into every line of code. "We're using Next.js because everyone does" is not a decision; it's a default. The team that defaults pays compounding interest on every constraint the framework imposes.

**Pass condition:** Decision + ≥2 alternatives + rationale + a stated success criterion (how will you know in 6 months whether this was the right call?).

**Adversarial counter-pass:** Name a project requirement that *this* framework makes harder than the alternative would (every framework has one — naming it forces honest trade-off acknowledgment). If you can't name any, you haven't actually compared.

**Output:** `docs/adr/0001-framework-choice.md`.

### Pass 2 — Persistence + tenancy model

**Check:** What stores what data?

- Primary DB (Postgres? MySQL? Mongo?)
- Cache / session store (Redis? in-memory? Memcached?)
- Object / blob storage (S3? local FS? CDN-fronted?)
- Search index (if any — Elasticsearch? Postgres FTS? Algolia?)
- Queue / event bus (if any — Redis? Kafka? SQS? in-process?)

And **tenancy** — the single most consequential decision:

- Single-tenant (one DB per customer)
- Multi-tenant via row-level security (RLS, `tenant_id` column, RLS policies)
- Multi-tenant via schema-per-tenant
- Multi-tenant via DB-per-tenant

**Why:** Tenancy decisions are the hardest to reverse. Switching from "shared DB with `tenant_id` column" to RLS is a multi-month project on a live system. Picking wrong here is expensive forever.

**Pass condition:** Each store named with its purpose, capacity expectation, isolation guarantee, and backup/restore strategy. Tenancy model named with the rationale (cost / isolation / blast-radius trade-offs explicit).

**Adversarial counter-pass:** Pick the tenancy model and answer: "What does a tenant-data-leak post-mortem look like in this model?" If the answer is "shouldn't happen if we don't bug" — the model is too permissive. The model should make tenant-data leaks structurally hard, not just rule-following hard.

**Output:** `docs/adr/0002-persistence-and-tenancy.md`.

### Pass 3 — Trust boundaries + auth model + data classification

**Check:**

- **Trust boundaries** — draw the diagram. Where does untrusted input enter? Where do privilege transitions happen (anonymous → authenticated → admin)? Where does data cross a network boundary?
- **Auth model** — session cookies, JWT, OAuth, mTLS, hybrid? Who issues tokens? Who validates? Where do they live (cookie? localStorage? bearer header — and why)?
- **Authorization model** — RBAC, ABAC, ReBAC, per-resource ACL? Where's the decision point (middleware? per-handler? per-query?)?
- **Data classification** — PII / PHI / financial / regulated / public. Each class with handling rules (encryption at rest? at transit? logging redaction? retention policy?).

**Why:** Security is structural, not ceremonial. Decisions made at this gate dictate which classes of vulnerability are even *possible* in your system. JWT in localStorage means XSS is catastrophic; session cookie with `HttpOnly` + `Secure` + `SameSite=Strict` makes XSS a contained class.

**Pass condition:** Trust-boundary diagram exists. Auth + authz model named with the canonical "where does the principal come from for every request?" answer. Data classes enumerated with handling rules per class.

**Adversarial counter-pass:** For each class of data, name a path through the system where it could plausibly leak. If the answer is "the code is supposed to redact" — the leak is one bug away. Make the leak *structurally* hard (DB-level encryption, per-class table separation, log filters at the appender).

**Output:** `docs/adr/0003-auth-and-data-classification.md`. This ADR is the load-bearing input for `apex:threat-model` (per-feature) and `apex:security-review` (PR-time).

### Pass 4 — Observability + deployment shape

**Check:**

- **Logging** — structured? destination? PII filter? log levels? retention?
- **Metrics** — what's the metrics stack? SLOs defined?
- **Tracing** — distributed tracing enabled? sampling rate? propagation?
- **Errors** — error-tracking service? alerting rules? on-call expectations?
- **Deploy model** — monolith? microservices? serverless? container orchestration?
- **Rollout strategy** — blue/green? rolling? canary? feature flags?
- **Environments** — dev/staging/prod or more? promotion gates?

**Why:** A system you can't observe is a system you can't operate. A deploy model you can't roll back is a deploy model that punishes you for every release. These are the operational tax that compounds across every feature.

**Pass condition:** Observability stack named with the "how would I debug a production incident?" answer. Deploy shape named with the rollback story.

**Adversarial counter-pass:** Pick a non-trivial production incident (e.g. "users report transactions vanishing"). Walk through the observability stack — can you actually find the root cause in 30 min? If you can't, observability is missing something.

**Output:** `docs/adr/0004-observability-and-deploy.md`.

### Pass 5 — Design system + UI foundation

**Check:**

- Component library (custom? Radix? shadcn? Material? Ant?)
- Design tokens (colors, typography, spacing — how shared?)
- Accessibility baseline (WCAG level? keyboard nav? screen-reader testing?)
- Internationalization (single locale? i18n from day 1? right-to-left?)
- Brand identity (logo, voice, motion language)

**Why:** Design choices made at component level become the team's vocabulary. Switching component libraries mid-project is brutal; choosing well early makes every feature faster.

**Pass condition:** Component library named with rationale. Design tokens documented. A11y baseline stated.

**Adversarial counter-pass:** Pick a non-trivial UI scenario (multi-step form with autosave + error recovery). Can the chosen system express it without custom workarounds? If not, the system is too opinionated for your domain.

**Output:** `docs/adr/0005-design-system.md`.

### Pass 6 — Branch / release / PR-stack strategy

**Check:**

- Branch model — trunk-based? GitFlow? release branches?
- PR-stack discipline — `apex:pr-discipline` §3 (layered PR stacks ≤400 LOC) applied; how does the team handle stacks across multiple PRs?
- Merge policy — squash? merge commit? rebase?
- Release cadence — continuous? weekly? quarterly?
- Versioning — semver? calver? rolling?
- Hotfix model — how does a fix reach production fast?

**Why:** Branch strategy shapes velocity and rollback shape. Pick wrong and every release is a multi-day coordination ritual.

**Pass condition:** Branch strategy + merge policy + release cadence + hotfix model all named.

**Adversarial counter-pass:** A P0 bug ships to prod at 3 PM Friday. Walk through the hotfix flow per this strategy. If the flow has >3 steps or any step requires coordination, the strategy is too heavy.

**Output:** `docs/adr/0006-branch-and-release.md`.

### Pass 7 — System-level threat model

**Check:** Apply STRIDE (Spoofing / Tampering / Repudiation / Information disclosure / Denial of service / Elevation of privilege) at the SYSTEM boundary, using Pass 3's trust boundaries + data classification as input. For each trust boundary:

- **Spoofing** — can an attacker impersonate a legitimate principal? (auth model from Pass 3)
- **Tampering** — can an attacker modify data in transit, at rest, or in motion?
- **Repudiation** — can a principal deny they did something? (audit log from Pass 4)
- **Information disclosure** — can an attacker read data they shouldn't? (data classification from Pass 3, tenancy from Pass 2)
- **Denial of service** — what's the rate-limit / circuit-breaker / quota model?
- **Elevation of privilege** — can a low-privilege principal become high-privilege?

**Why:** Per-feature threat modeling (`apex:threat-model`) inherits the system-level model. If the system-level model is missing or weak, per-feature models will re-derive the same questions inconsistently. Doing it once at architecture time is cheaper than doing it badly N times.

**Pass condition:** Each STRIDE category has a named system-level mitigation referencing the architecture choices (auth model handles Spoofing, audit log handles Repudiation, tenancy + RLS handles Information disclosure, etc.).

**Adversarial counter-pass:** For each STRIDE category, name a residual risk the architecture *doesn't* mitigate. If you can name none, you're not being honest — every architecture has residual risks; they should be explicit, not hidden.

**Output:** `docs/adr/0007-system-threat-model.md`. This is the load-bearing input for `apex:threat-model` (per-feature) and `apex:security-review` (PR-time).

## Architecture freeze readiness

After all 7 passes + adversarial counter-passes + the 7 ADRs are written, **freeze the architecture**. From this moment:

- Feature PRDs are scoped against this architecture
- `apex:design-feature` Pass 4 (integration with existing surface) checks each feature for fit
- A feature that doesn't fit triggers an architecture amendment via `apex:adr-review` (writing a new ADR or updating an existing one)
- Silent reshaping of the architecture during implementation is a process failure

## Output structure

```
docs/adr/
├── 0001-framework-choice.md
├── 0002-persistence-and-tenancy.md
├── 0003-auth-and-data-classification.md
├── 0004-observability-and-deploy.md
├── 0005-design-system.md
├── 0006-branch-and-release.md
├── 0007-system-threat-model.md
└── README.md      ← index + freeze status
```

Each ADR follows a canonical structure (`apex:adr-review` audits this). New ADRs from amendments use the next available number; superseded ADRs get a "Superseded by ADR-NNNN" link, not deleted.

## Hand-off to feature work

Once the architecture is frozen:

- `apex:prd-review` runs against the frozen architecture — scenarios that contradict the architecture surface as Pass 3 (unknowns) or Pass 5 (sequencing) findings
- `apex:design-feature` Pass 4 checks each feature for architecture fit
- `apex:threat-model` per-feature builds on Pass 7's system-level model
- `apex:security-review` PR-time audits the implementation against Passes 3 + 7
