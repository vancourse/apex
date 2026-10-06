---
name: postgres-review
description: Postgres schema, RLS, indexing and SQL review rules. Load the rule file for the task at hand.
---

# Postgres Review Rules

Generic, cross-project PostgreSQL rules. Read only the rule file(s) matching
the current task — do not load all of them.

This skill covers **Postgres-internal** concerns, starting with schema design.
Indexing, migrations, transactions + locking, and observability are planned
rule files (see 'Coming next' below). For **RLS and multi-tenant isolation**,
invoke `rails:multi-tenancy` directly. For **ORM / Python-side** concerns
(N+1, connection pooling, cache deduplication, idempotency tests, pagination),
load `rails:python-review/rules/db-and-sql.md` instead. The skills are designed
to be loaded together when a change crosses the boundary.

## Routing table

| Task touches...                                                                                                              | Read                                              |
| -------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| Column data types, constraints, generated columns, JSONB strategy, primary keys, composite-UNIQUE-as-FK-enforcer pattern   | `rules/schema-design.md`                          |
| **Multi-tenant isolation** (Postgres RLS policies, schema-per-tenant, DB-per-tenant, app-layer filtering, tenant-context propagation, cross-tenant FK enforcement) | invoke **`rails:multi-tenancy`**                   |
| **PR-time security audit** (secrets / authn+authz / input val + output enc / dep vuln + supply chain / audit log)          | invoke **`rails:security-review`**                 |
| **Design-phase threat modeling** (STRIDE against the feature's attack surface)                                             | invoke **`rails:threat-model`**                    |
| **Architecture-level persistence + tenancy decision** (which role model, which RLS strategy, which migration tool)         | invoke **`rails:architecture-design`** Pass 2      |

## Coming next (planned)

The skill is being expanded incrementally. Planned rule files, with the
topics they will cover:

- `rules/indexing.md` — B-tree / GIN / GiST / BRIN / partial / covering index choice, `EXPLAIN (ANALYZE, BUFFERS)` reading, join + CTE strategy.
- `rules/migrations.md` — migration ordering, expand/contract, online DDL, backfill discipline, idempotent SQL.
- `rules/transactions-locking.md` — isolation levels, advisory locks, `FOR UPDATE SKIP LOCKED`, deadlock patterns, statement timeouts.
- `rules/observability.md` — `pg_stat_statements`, `auto_explain`, slow-query log, vacuum + autovacuum tuning.

Until those land, defer to `rails:python-review/rules/db-and-sql.md` for the
Python-side patterns that touch the same topics (pagination, N+1, pooling),
and to `rails:architecture-design` Pass 2 for foundational decisions.

## When this fires

Currently (`rules/schema-design.md` is the only rule file today):
- Designing or reviewing a new table / column / constraint / index
- Writing hand-rolled SQL beyond ORM convenience methods

Planned (once additional rule files land):
- Authoring or reviewing a migration → `rules/migrations.md`
- Investigating a slow query, deadlock, or vacuum issue → `rules/observability.md`, `rules/transactions-locking.md`

For RLS and multi-tenant isolation, invoke **`rails:multi-tenancy`** directly.

## When this does NOT fire

- `session.query(Foo).filter_by(...)` and similar ORM helpers — load
  `rails:python-review/rules/db-and-sql.md` instead.
- Routine CRUD the ORM handles trivially.

## Project-specific overlays

Project-specific Postgres rules — tenant role names, GUC names, the canonical
session helper, the explicit RLS-protected table list, the composite-FK
patterns that are load-bearing in *your* schema — belong in a per-repo
overlay loaded **in addition** to this skill. Example path:
`.claude/skills/<project>-pre-pr-check/rules/postgres-specifics.md`
(see your project's pre-PR skill).
