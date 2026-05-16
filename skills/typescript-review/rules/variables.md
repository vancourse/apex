# Variables & Constants

Mutation discipline and module-level constants.

## Prefer `const` — No `let` Unless Necessary

**Rule:** Don't use `let` unless truly required for performance. Use ternary, IIFE, or early return instead.

```typescript
// ❌ BAD
let status;
if (isActive) status = 'active';
else status = 'inactive';

// ✅ GOOD: ternary
const status = isActive ? 'active' : 'inactive';

// ✅ GOOD: IIFE for complex logic
const status = (() => {
  if (isActive) return 'active';
  if (isPending) return 'pending';
  return 'inactive';
})();
```

## Module-Level Constants for Lookup Tables

**When:** Defining a `Record`, `Map`, or object literal used purely as a lookup table.
**Rule:** Define it at module level, not inside a function body. Function-scoped lookup objects are reconstructed on every call.

```typescript
// ❌ BAD: rebuilt on every call
const mutationFn = async (payload) => {
  const typeMap: Record<string, string> = {
    TEXT: 'string',
    INTEGER: 'integer',
  };
  return typeMap[payload.type] ?? 'string';
};

// ✅ GOOD: defined once
const SQL_TO_JSON_SCHEMA_TYPE: Record<string, string> = {
  TEXT: 'string',
  INTEGER: 'integer',
} as const;

const mutationFn = async (payload) => SQL_TO_JSON_SCHEMA_TYPE[payload.type] ?? 'string';
```

## snake_case for Data Files — camelCase for Code

**Rule:** Functions and variables use camelCase. Data in JSON/config files uses snake_case to match server conventions.
