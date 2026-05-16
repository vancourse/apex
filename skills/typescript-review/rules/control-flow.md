# Control Flow

Early returns, exhaustive switches, and readability.

## Early Returns to Reduce Nesting

**Rule:** Always prefer early returns over nested `if/else` blocks.

## Narrow-and-Return for Variant Components

**When:** Rendering a member of a discriminated union (one variant per component file).
**Rule:** First statement of the component narrows on the discriminator and returns `null` otherwise. The parent does the dispatch with simple `&&` checks — no nested ternaries on `detail.type` and no central component with a `switch` over every variant.
**Why:** Each variant component fits in 30 lines and is independently scannable. The discriminator does the work; no defensive null-spreading inside.
**How to apply:**
```typescript
// Variant component — first statement narrows + returns:
const StepProgressDetail: FC<{ detail: ToolProgressDetail }> = ({ detail }) => {
  if (!detail || detail.type !== 'step_progress') return null;
  // ...rest of the component knows detail is StepProgress
};

// Parent — flat dispatch, no nesting:
{content.detail?.type === 'step_progress' && <StepProgressDetail detail={content.detail} />}
{content.detail?.type === 'field_update' && <FieldUpdateDetail detail={content.detail} />}
```

## Exhaustive Switch With `satisfies never`

**When:** Writing a switch over a union/literal type.
**Rule:** Add a default branch that asserts `satisfies never` and throws. This catches unhandled cases at compile time.

```typescript
switch (status) {
  case 'pending':
    return handlePending();
  case 'completed':
    return handleCompleted();
  default:
    status satisfies never;
    throw new Error('Unknown status');
}
```

## Extract Complex Conditions to Named Variables

**Rule:** `const isValid = a && b && c` — then `if (isValid)`. Never `if (a && b && c && d)` inline for non-trivial conditions.

## Avoid Rightward Drift — Refactor Into Smaller Functions

**Rule:** Deep nesting is a signal to extract. Each level of nesting costs the reader's working memory.

## IIFEs for Isolated Error Handling

**When:** A branch needs its own error handling scope without creating a named function.
**Rule:** Use an IIFE to isolate the logic:

```typescript
const result = await (async (): Promise<Result<Data>> => {
  // isolated logic with its own error handling
})();
```
