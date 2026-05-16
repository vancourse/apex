# Zod & Validation

Schema definitions, type inference, client/server sync.

## Schema and Inferred Type Share the Same PascalCase Name

**Rule:** Use declaration merging so the schema constant and its inferred type are co-located under the same name.

```typescript
const ApiKeyConfig = z.object({ ... });
type ApiKeyConfig = z.infer<typeof ApiKeyConfig>;
```

## Client and Server Validation Must Stay in Sync

**Rule:** Server is the source of truth for data integrity. Client validation is UX — not a security boundary. When updating a server schema, check if the client schema needs updating too.

## Use `.trim()` on String Fields

**Rule:** Apply `.trim()` to string fields to prevent whitespace-only values passing validation.

```typescript
// Client
const schema = z.object({
  name: z.string().trim().min(1, 'Name is required').max(100, 'Name must be at most 100 characters'),
});

// Server
z.string().trim().min(1).max(100)
```

## Client Validation Must Have Meaningful Error Messages

**Rule:** User-facing validation errors must explain what went wrong. Empty `.min(1)` errors are not sufficient on the client.

## `parse` vs `safeParse`

**Rule:** Use `safeParse` when you want to handle errors as a `Result`. Use `parse` (which throws) only at system boundaries where you want a hard failure on invalid data.

## Discriminators for Union Schemas

**When:** Defining a union schema with a common tag field.
**Rule:** Use `z.discriminatedUnion('type', [...])` instead of `z.union([...])`. Discriminated unions give better error messages and faster parsing.

## Refinements for Cross-Field Validation

**When:** Validation depends on multiple fields (e.g., "if type is X, field Y must be present").
**Rule:** Use `.refine()` or `.superRefine()` instead of post-parse manual checks.
