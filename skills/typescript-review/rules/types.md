# Types

TypeScript type system discipline — no `any`, no casts, invariant-encoding.

## No `as` Casts — Fix Types at the Source

**Rule:** `as SomeType` is almost always a symptom of a broken type upstream. Fix the source type instead of casting at usage sites.

## No `any` — Flag and Fix

**Rule:** Never introduce `any`. Flag existing `any` types and offer to fix them. Never move an `any` around to resolve a type error — that propagates the hole.

## Don't Rewrite or Copy Types — Import From the Owner

**Rule:** Import types from their owning file. Don't copy a type definition into a new file to avoid a dependency.

## Generics Prefixed With `T`

**Rule:** Generic type parameters use `T` followed by a descriptive name: `TUserId`, `TPayload`, `TResult`.

## `satisfies` for Type-Checked Literals Without Widening

**When:** You need to verify a value matches a type but preserve the narrowed literal.
```typescript
const config = { timeout: 1000 } satisfies Config;
```

## `as const` for Literal Types

**When:** Defining a constant that should retain its literal type.
```typescript
const API_KEY_PREFIX = 's4w' as const;
```

## Encode Finite State Sets as Literal Unions — Never Raw `string`

**When:** A field takes values from a finite set (environment, dialect, role, status, kind).
**Rule:** Type it as a literal union or an enum. Never a bare `string`. Prefer a typed field over stuffing the value into a `Record<string, unknown>` bag.
**Why:** Literal unions enable exhaustive checks in `switch`, flow to UI components as dropdown options, and survive refactors.

```typescript
// ❌ BAD
type Config = { environment: string; extra: Record<string, unknown> };

// ✅ GOOD
type Environment = "prod" | "test";
type Config = { environment: Environment; source: "manual" | "imported" };
```

## Discriminated Unions Over Nullable Fields

**When:** A value can be in multiple distinct states.
**Rule:** Prefer discriminated unions over all-nullable structs.
```typescript
type Result<T> =
  | { success: true; data: T }
  | { success: false; error: { code: string; message: string } };
```

## Wire-Format Symmetry With the Server

**When:** A TS discriminated union mirrors a server-side one (Python `Literal[...]`, Pydantic discriminator, JSON-Schema `enum`).
**Rule:** The discriminator literal strings must match **byte-for-byte**: same casing, same snake_case/kebab-case choice, same field name (`type`, `kind`, `event_type`). Treat any drift as a bug, not a translation step. When in doubt, validate with a roundtrip test.
**Why:** The client narrows on the same string the server emits. A casing mismatch silently fails to narrow — the variant component falls into the default case and renders nothing, with no type error to catch it.
**How to apply:**
```typescript
// Python emits Literal["step_progress"]; TS narrows on the same literal:
if (!detail || detail.type !== 'step_progress') return null;
```
Do not lowercase, kebab-case, or "translate" the wire string at the seam. If the server uses `event_type`, the client uses `event_type` — not `eventType`.

## Prefer Explicit `null` Over `undefined` in Return Types

**Rule:** Return `null` (not `undefined`) to signal absence of data in function return types. Keeps the absence intentional and visible.

## Branded Types — Update at the Interface Layer

**When:** Adding a branded type (e.g., `SecretDataReference<string>`).
**Rule:** Update the database/interface types to use it directly. Don't cast at every usage site.

## Types Should Encode Invariants — Not Initial State

**When:** A type has all nullable fields.
**Rule:** That usually means the type was designed for the empty/initial state, not the valid domain state. Use a discriminated union to separate states.

```typescript
// ❌ BAD: every field nullable — nothing is guaranteed
type DocumentClassification = {
  documentType: string | null;
  systemPrompt: string | null;
};

// ✅ GOOD: discriminated union — unclassified vs classified
type DocumentClassification =
  | { classified: false }
  | { classified: true; documentType: string; systemPrompt: string | null };
```

## Don't Use `?: T | null` — Pick One Absence Representation

**Rule:** Using both `?` (undefined) and `| null` creates three possible states. Choose one:
- `?: T` — optional (absence = undefined)
- `T | null` — required, value may be absent

Never both on the same field unless you genuinely need to distinguish "not provided" from "explicitly cleared".

```typescript
// ❌ BAD: three states
type SchemaMetadata = { documentType?: string | null };

// ✅ GOOD
type SchemaMetadata = { documentType?: string };   // or
type SchemaMetadata = { documentType: string | null };
```
