---
name: python-review
description: Python review rules (types, SQL, async, tests, errors, security). Load the rule file for the task at hand.
---

# Python Review Rules

Generic, cross-project Python rules. Read only the rule file(s) matching
the current task — do not load all of them.

## Routing table

| Task touches...                                                              | Read                                        |
| ---------------------------------------------------------------------------- | ------------------------------------------- |
| Class/module layering, SOLID, GoF patterns, service-class signal             | `rules/architecture.md`                     |
| Pydantic models, dataclasses, typing, generics, state transitions            | `rules/types-and-models.md`                 |
| SQL queries, ORM, N+1, pagination, caching, connection pools, idempotency    | `rules/db-and-sql.md`                       |
| **Postgres-internal** topics (schema design, indexing, migrations, transactions + locking, observability) | invoke **`rails:postgres-review`** |
| **Multi-tenant isolation** (Postgres RLS, schema-per-tenant, DB-per-tenant, app-layer filtering, tenant-context propagation) | invoke **`rails:multi-tenancy`** |
| asyncio tasks, locks, timeouts, sync-in-async, SSE streaming                 | `rules/async-concurrency.md`                |
| **Test methodology** (8-layer model, mocking policy, PRD↔mirror, scenarios-first, CI tiering, isolation, 18 rules) | invoke **`rails:test-strategy`** |
| Python testing tooling (pytest stubs vs MagicMock, async fixture typing, .model_dump test data, transaction-rollback fixture, pytest-xdist) | `rules/testing.md`                          |
| Exception specificity, fail-fast, silent data loss, `assert` in production   | `rules/error-handling.md`                   |
| `structlog`, log levels, PII redaction, error IDs, docstring contracts       | `rules/logging-observability.md`            |
| **PR-time security audit** (secrets / authn+authz / input validation + output encoding / dep vuln + supply chain / audit log) | invoke **`rails:security-review`** |
| **Design-phase threat modeling** (STRIDE against feature attack surface) | invoke **`rails:threat-model`** |
| Python security tooling (secrets in `os.environ`, Pydantic boundary, parameterized SQL, filename sanitization, path-traversal, LLM delimitation, parsing bounds) | `rules/security.md`                         |
| FastAPI routes, request validation, partial success, pagination envelopes    | `rules/api-design.md`                       |
| Imports, layer placement, dead code, docstring drift, dependency management  | `rules/code-hygiene.md`                     |
| AI-assisted code (`getattr`/`hasattr`/`isinstance` speculation, SDK guards)  | `rules/ai-code-smells.md`                   |

For PR sizing, the blocker-artifact protocol, and review-reply discipline, see the top-level `pr-discipline` skill — it covers all languages, and its companion [`rules/responding-to-review.md`](../../rules/responding-to-review.md) holds the canonical review-comment protocol.

## When multiple topics apply

Pick the dominant one. Don't load everything. If a rule lives in two
topics, the dominant file owns it and others cross-reference by name.

## Project-specific overlays

Project-specific rules (layering conventions, package bans, internal API
names, canonical wrapper tables) live in each repo's own
`.claude/my-guidelines/python-review.md`. Load that IN ADDITION when
working in that project.
