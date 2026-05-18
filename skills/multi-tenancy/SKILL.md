---
name: multi-tenancy
description: Multi-tenant isolation strategies and their per-strategy review rules — Postgres RLS today; schema-per-tenant, database-per-tenant, application-layer filtering, and tenant-context propagation are planned rule files (see SKILL.md 'Coming next'). Routing table inside; load only the rule file matching the strategy in use. Fires when designing or reviewing tenant isolation, authoring an RLS policy, choosing a tenancy model for a new service, or auditing cross-tenant data leakage risk. For the architecture-level decision (which strategy to use), invoke apex:architecture-design Pass 2. Pairs with apex:postgres-review for Postgres-internal concerns (schema, indexing, migrations) that any tenant-scoped table also depends on. Keywords: multi-tenant, multitenancy, tenancy, isolation, rls, row level security, schema-per-tenant, database-per-tenant, tenant context, tenant id, cross-tenant.
---

# Multi-Tenancy Review Rules

Multi-tenancy is a cross-cutting architectural concern, not a Postgres
flavor. The choice of strategy (RLS / schema-per-tenant / DB-per-tenant /
app-layer filtering / hybrid) constrains every subsequent decision about
schema, queries, migrations, observability, billing, data export, and
incident response. This skill covers the *per-strategy review rules* — the
detail you need once a strategy is picked.

For the **strategy-choice decision itself** — which model fits which
business, blast-radius, isolation-strength, and migration-cost constraints —
invoke `apex:architecture-design` Pass 2 (Persistence + tenancy). That gate
produces an ADR that this skill's per-strategy rules then operationalize.

## Routing table

| Task touches...                                                                                                                | Read                                              |
| ------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------- |
| Postgres RLS policies, non-privileged role pattern, `set_config(...)` / `SET LOCAL` for tenant GUC, `FORCE ROW LEVEL SECURITY`, cross-tenant FK enforcement | `rules/postgres-rls.md`                           |
| **Architecture-level tenancy-strategy decision** (which model: RLS / schema-per-tenant / DB-per-tenant / app-layer / hybrid)   | invoke **`apex:architecture-design`** Pass 2      |
| **Postgres-internal** concerns shared by all tenant-scoped tables (schema design, indexing, migrations, transactions, vacuum) | invoke **`apex:postgres-review`**                 |
| **PR-time security audit** (verifies the implementation against the tenancy + auth model from architecture-design Pass 3 + 7) | invoke **`apex:security-review`**                 |
| **Design-phase threat modeling** (STRIDE against the feature's tenant-boundary surface)                                        | invoke **`apex:threat-model`**                    |

## Coming next (planned)

The skill is being expanded incrementally. Planned rule files, with the
topics they will cover:

- `rules/schema-per-tenant.md` — per-tenant schemas, search_path discipline, role-grant matrix, migration fan-out, cross-tenant analytics with `pg_dump`/replication.
- `rules/database-per-tenant.md` — connection pooling per database, tenant-routing layer, shared-vs-isolated maintenance windows, backup/restore granularity, the "noisy neighbor" trade.
- `rules/tenant-context-propagation.md` — request → service → DB → queue → background job → log line. Header → middleware → request-context → DB session GUC. AsyncIO context-vars vs thread-locals vs explicit-pass. Failure mode: tenant-leak in async fan-out.
- `rules/tenant-data-export.md` — per-tenant snapshot, GDPR data-export, cross-tenant analytics with safe joins, "show me everything tenant X has" SQL recipes.
- `rules/billing-aware-isolation.md` — per-plan rate limits, per-tenant quota, noisy-neighbor mitigation, premium-tier hardware affinity.

Until those land, defer to `apex:architecture-design` Pass 2 for the
strategy-choice decision and to `rules/postgres-rls.md` for the canonical
worked example of the RLS strategy.

## When this fires

- Designing or reviewing a new tenant-scoped table, query, or service
- Authoring or reviewing an RLS policy
- Choosing or amending a tenancy strategy for a new sub-system
- Auditing cross-tenant leak risk during PR review
- Investigating a suspected tenant-data exposure incident

## When this does NOT fire

- Single-tenant systems with no per-customer isolation requirement.
- B2C applications where users are not tenants of each other.
- Internal-tools or one-off scripts that operate against a single dataset.

In those cases, `apex:postgres-review` covers the Postgres concerns
directly; nothing else from this skill applies.

## Project-specific overlays

Project-specific multi-tenancy rules — the project's chosen non-privileged
role name, the canonical `tenant_db()` helper signature, the explicit
RLS-protected table list, the composite-FK patterns that are load-bearing
in *your* schema — belong in a per-repo overlay loaded **in addition** to
this skill. Example path:
`.claude/skills/<project>-pre-pr-check/rules/multi-tenancy-specifics.md`
(see your project's pre-PR skill).
