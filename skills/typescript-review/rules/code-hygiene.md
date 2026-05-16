# Code Hygiene

Exports, organization, dead code, and PR discipline.

## Look Around First — Check Existing Patterns Before Building

**Rule:** Before introducing a new helper, pattern, or utility, check for existing usage in the codebase. Mimic existing patterns. If a refactoring would improve things, raise it with clear PROs/CONs.

Before writing any schema/JSON manipulation, type conversion, or data transformation, grep the codebase for an existing utility. Reinventing creates divergence — two implementations where one already handles edge cases.

## Keep It Simple — No Premature Abstraction

**Rule:** Readability trumps cleverness. Avoid common over-engineering:
- `useMemo`/`useCallback` for values that don't need memoization
- IIFEs when a simple ternary suffices
- Abstractions for one-time operations
- Comments explaining self-evident code

If complexity is truly needed, justify it with a comment or test.

## Latest Dependency Versions

**Rule:** When installing a new dependency, use the latest stable version. Don't pin to an older version unless there's a concrete reason.

## Business Logic Lives on the Backend

**Rule:** Domain rules, state enumerations, model catalogs, pipeline/route definitions, and matching/identity logic live on the backend. The frontend consumes them via the API and renders them.
**Why:** Split-brain logic drifts — every copy of a rule is a future bug. When the backend changes its model list or adds a state, the frontend discovers it from the API instead of shipping a parallel change.

Red flags in a frontend PR:
- Hardcoded lists of models/environments/statuses the backend also knows
- Pipeline stage names defined in TS that the Python layer owns
- Treating a typed tool-argument payload as `Record<string, unknown>` instead of using the generated OpenAPI type

## Named Exports Only — No Default Exports

**Rule:** Always use named exports. Default exports break barrel re-exporting and make refactoring harder.

## Never Export Without a Present Consumer

**Rule:** Never export a symbol unless a file outside the current module imports it in the same PR. If scaffolding for a stacked PR, add `// Used by PR #N` and remove the export if that PR never lands.

**Check:** Grep every new `export` to confirm it has an importer.

## Barrel Exports With Explicit Re-Exports

**Rule:** Use barrel exports but always list exports explicitly. Never `export * from './module'`.

## Utils Placement — Lowest Common Ancestor

- Single consumer: next to the consuming folder
- Sibling consumers: parent level
- Codebase-wide: root level
- Single `utils.ts` unless multiple logical groups exist

## Ordering — Follow Existing Conventions

**Rule:** When adding keys to objects or enum values, follow existing ordering (often alphabetical). For new structures, prefer lexicographic order.

## Remove Dev Scaffolding Before Opening a PR

**Rule:** Search for `devtools`, `console.log`, `console.error` (outside catch blocks), and `debugger` before submitting. These are never appropriate in production code.

```typescript
// ❌ BAD: devtools middleware in production store
export const useMyStore = create<State>()(
  devtools((set) => ({ ... }))  // remove before PR
);
```

## Don't Ship Dead Stores or Unused Components

**Rule:** Verify every new file has at least one consumer. If it's a planned stub, note it with `// TODO(PR #N)`.

## Reviewer Blockers Need Artifact Proof

**Rule:** A blocker is only resolved when the PR contains: a code change at the referenced location, a new/updated test, or an explicit reviewer-approved rationale. Never reply "addressed" without a diff.

Before posting "addressed", include:
1. blocker text
2. changed file path(s)
3. proof artifact (diff snippet or test name)
4. verification command run

## Every Review Reply Must Map to a Diff

- Status: fixed / intentionally deferred / question
- Exact file path(s) changed
- If deferred: ticket link and reason

## Store Business Logic Helpers Require Unit Tests

**Rule:** When modifying business-logic helpers (path traversal, update functions, schema transforms), add unit tests in the same PR. Minimum cases: happy path, invalid/no-op, edge case, regression.

## Pre-Submit Blocker Gate

**Before requesting re-review:**
1. List all blockers from reviewer summary
2. Confirm each has a merged code/test artifact
3. Do not ask for re-review if any blocker lacks an artifact
