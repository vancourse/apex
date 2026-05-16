---
name: typescript-review
description: Generic TypeScript/React code review rules — types, control flow, hooks, components, stores, testing, error handling, hygiene, AI code smells. Routing table inside; load only the rule file matching the current task. Fires when investigating a specific TS/React anti-pattern, auditing a diff for review, or planning a refactor — NOT for every TS/TSX edit. In BookBridge, prefer `bookbridge-pre-pr-check` as the entry point; it cross-references rule files here. Keywords: typescript anti-pattern, react review, code review, refactor, frontend review, hooks, zod, zustand, playwright.
---

# TypeScript & React Review Rules

Generic, cross-project TS/React rules. Read only the rule file(s) matching
the current task — do not load all of them.

## Routing table

| Task touches...                                               | Read                              |
| ------------------------------------------------------------- | --------------------------------- |
| Types, `any`, `as`, generics, branded, discriminated unions   | `rules/types.md`                  |
| Early returns, switch exhaustiveness, narrow-then-act         | `rules/control-flow.md`           |
| Arrow functions, object args, defaults, return types          | `rules/functions.md`              |
| `const`/`let`, module-level constants, naming                 | `rules/variables.md`              |
| Try/catch, Result pattern, `asError`, error codes, logging    | `rules/error-handling.md`         |
| Zod schemas, parse vs safeParse, discriminator, refinement    | `rules/zod-validation.md`         |
| React hooks — deps, stale closures, AbortController, cleanup  | `rules/react-hooks.md`            |
| React components — props, dialogs, mutations, routing, a11y   | `rules/react-components.md`       |
| Zustand (or similar) stores — atomic updates, cleanup         | `rules/zustand-stores.md`         |
| Playwright e2e — state-based waits, isolation, selectors      | `rules/playwright-e2e.md`         |
| Imports, dead code, speculative exports, PR discipline        | `rules/code-hygiene.md`           |
| AI-assisted code (speculative defaults, three-state null)     | `rules/ai-code-smells.md`         |
| FE doing server-domain work (classify, synthesise, transform) | `rules/frontend-backend-layering.md` |

## When multiple topics apply

Pick the dominant one. Don't load everything.

## Project-specific overlays

Project-specific rules (framework idioms, design-system components,
shared internal utilities) belong in a separate per-repo guideline file.
Load that in addition to these generic rules when working in that repo.

## Source of truth

The `rules/` files are the canonical reference.
