# React Components

Props, mutations, component ownership, routing, dialogs, and HTML semantics.

## Handler Naming — `handle` Prefix

**Rule:** Handlers are prefixed with `handle`: `handleSubmit`, `handleNameChange`, `handleDelete`.
Callback props use `on`: `onCardClick`, `onProviderFormSubmit`, `onApiKeyDelete`.

## `useCallback` Only for Stability Gains

**Rule:** Only wrap in `useCallback` when it's passed to a memoized child component or used in a dependency array. Don't wrap already-stable functions (React Query `mutate`, `invalidate`).

## Never Spread Props — Define Them Explicitly

**Rule:** `<Component {...props} />` hides what gets passed. Always define props explicitly.

## Required Props Over Optional

**Rule:** If a prop is always passed by every consumer, make it required. Optional props add conditional logic throughout the component with no benefit.

```typescript
// ❌ BAD: always passed but optional
type Props = { onCreate?: () => void };

// ✅ GOOD
type Props = { onCreate: () => void };
```

## Dialogs and Primary Consumers Should Own Their Mutations

**Rule:** Components that are the primary consumers of a mutation (create, edit, delete dialogs) should own the mutation internally. Parents should not pass mutation callbacks down.

```typescript
// ❌ BAD: parent owns mutation, passes callback
<CreateDialog onSubmit={async (name) => createMutation.mutateAsync({ name })} />

// ✅ GOOD: dialog owns mutation
<CreateDialog onClose={handleClose} tenantId={tenantId} />
```

## Route-Based Dialogs Internalize All Side Effects

**Rule:** Navigation, cache invalidation, and snackbars triggered by a dialog's lifecycle belong inside the dialog, not in the route.

## Mutations With `onSuccess`/`onError` Close to Usage

```typescript
updateMutation.mutate(
  { id, name },
  {
    onSuccess: () => onUpdated(),
    onError: (error) => addSnackbar({ message: error.message, variant: 'danger' }),
  },
);
```

## Route Loaders for Immediate Data Availability

**Rule:** Fetch required data in route loaders. Pass loader data as `initialData` to queries to keep them reactive while avoiding a loading flash.

## Route Structure — Parent at `.tsx`, Not `/index.tsx`

**Rule:** Parent routes with child dialogs at `path.tsx`, not `path/index.tsx`. Using `index.tsx` causes blank screens when a child dialog is open and the parent hasn't loaded.

## Dialogs — Single Instance, Memoized Content

**Rule:** Never conditionally return different `<Dialog>` components. Use one `<Dialog>` with memoized content. This preserves focus across state transitions.

## Dialogs — No Content Padding

**Rule:** `Dialog.Content` handles its own padding. Don't wrap children in `<Box p="$4">`.

## Forms — Primary Button First

**Rule:** The `primary` action button is always first in dialog action areas.

## Buttons — Semantic Variants

- Cancel: `variant="secondary"`
- Delete/destructive actions: `variant="destructive"`

## No Nested Interactive Elements

**Rule:** A `<button>`, `<a>`, or `as="button"` element must never contain other buttons, links, or form controls. Use `<div role="button" tabIndex={0}>` for clickable containers that need inner action buttons.

## Don't Show Silent State Transitions

**When:** An async operation transitions through loading → success → idle.
**Rule:** Error state must be visible. Never silently reset to idle on error — show the error state and let the user retry.

## Validate Save Is Gated on Validation Completion

**When:** A form has async/debounced validation.
**Rule:** Disable the Save button while `isValidating` is true — not just when there are errors.

```typescript
// ✅ GOOD
<Button disabled={isValidating || !!validationErrors.length || !!jsonParseError}>Save</Button>
```

## Guard Mutation Handlers Against Concurrent Calls

**When:** A handler triggers an async mutation.
**Rule:** Check `isSubmitting` (or `mutation.isPending`) before firing. Double-clicks cause overlapping requests.

## Decompose Monolith Components

**Rule:** Components over ~400 lines handling multiple concerns (state + UI + lifecycle + I/O) should be split. Extract section subcomponents; extract lifecycle and data-fetch logic into dedicated hooks.

## Styling — Theme Tokens Over Hardcoded Values

**Rule:** `theme.colors.*`, `theme.fonts.*` — never `#1a1a1a` or `monospace`.

## Component Structure

- Don't wrap in `<Box>` if it adds no styling
- Separate loading from empty states — don't combine `if (isLoading || !data)`
- Pass objects directly when props match the shape; don't destructure and reconstruct

## Delete Confirmations — Use a Shared Confirm Hook

**Rule:** Destructive actions go through a shared confirmation hook/component (project-specific). Don't hand-roll `window.confirm` or ad-hoc confirm dialogs per feature.

## Prefer Design-System Primitives Over Hand-Rolled Elements

**Rule:** If the project has a design system (Button, Dialog, Table), use it instead of raw `<button>`, `<table>`, or re-styled `<div>`s. Hand-rolled variants drift from the system's accessibility, theming, and keyboard behavior.
