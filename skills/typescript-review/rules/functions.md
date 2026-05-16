# Functions

Signatures, argument patterns, naming, and return types.

## Arrow Function Notation

**Rule:** Use arrow functions (`const fn = () => ...`), not `function` declarations, for consistent `this` semantics.

## Always Type the Return Explicitly

**Rule:** Annotate every function's return type. Relying on inference hides breaking changes and makes call sites harder to read.

## Classes Only When State Persistence Is Needed

**Rule:** Prefer plain functions. Use a class only when it needs to hold state that persists across calls.

## Object Arguments for Multiple Parameters

**When:** A function takes 2+ parameters of similar or identical types.
**Rule:** Use a single object argument. Positional arguments of the same type are easily swapped.

```typescript
// ❌ BAD: two strings are easily swapped
const createUser = (firstName: string, lastName: string): User => ...

// ✅ GOOD
const createUser = ({ firstName, lastName }: { firstName: string; lastName: string }): User => ...
```

**Exception:** Two arguments whose types can't be mistaken (e.g., `(file: Buffer, type: string)`) are fine positional.

## Inline Argument Types — No Single-Use Aliases

**Rule:** Use inline types for function arguments unless the type is used in multiple places.

```typescript
// ❌ BAD: single-use alias
type UserInput = { name: string };
const updateUser = (input: UserInput): User => ...

// ✅ GOOD
const updateUser = ({ name }: { name: string }): User => ...
```

## Never Default Argument Values — Use Optional Instead

**Rule:** `options?: { limit?: number }` not `options = { limit: 20 }`. Default values create implicit behavior that callers can't see at the call site.

## Context First Argument

**When:** A `context` pattern exists in the codebase (monitoring, database).
**Rule:** `context` is always the first argument.

## Descriptive Names — Action-Oriented

**Rule:** `setLastUsedAt` not `touchApiKey`. `handleDelete` not `onClick2`.
- camelCase for functions and variables
- Avoid `res`, `result`, `data` as variable names — prefer `userListResult`, `retrievedApiKey`
