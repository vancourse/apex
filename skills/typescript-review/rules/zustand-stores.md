# Zustand Stores

Atomic updates, state consistency, navigation cleanup, and test coverage.

## Atomic Updates — Never Split Related State Across Two `set()` Calls

**Rule:** When updating related fields (data + status + derivedValue), always update them in a single `set({...})`. Two separate calls let a component render between them and see an inconsistent state.

```typescript
// ❌ BAD: renders in-between can see status=complete with stale data
set({ status: 'complete' });
set({ data: newData });

// ✅ GOOD: single atomic update
set({ status: 'complete', data: newData, derivedValue: newData.computed });
```

## Clear All Related Fields on Reset

**When:** Resetting state for a new session or operation.
**Rule:** Every related field must be cleared. Forgetting one leaves the UI in an inconsistent state.

**Also watch:** Reset functions that miss newly-added fields; `handleResetAll` clearing an array but leaving the index at `0` instead of `-1` (sentinel for "no selection").

## Reset Store on Navigation Away

**When:** A store holds session-specific data (results, file refs, streaming state).
**Rule:** Reset on unmount or session change. Stale store data renders on return, and a still-running stream can overwrite it.

```typescript
// ✅ GOOD
useEffect(() => {
  return () => {
    resetSessionStore();
    clearPendingOperations();
  };
}, [sessionId]);
```

## Store Business Logic Helpers Require Unit Tests

**When:** Adding or modifying business-logic helpers in a store (path traversal, updater functions, schema transforms).
**Rule:** Add unit tests in the same PR.

**Minimum cases:** happy path, invalid/no-op path, edge case (nested/array/object), regression scenario from a review comment.

## Don't Ship Dead Stores or Unused Components

**Rule:** Before submitting a PR, verify every new store/component file has at least one consumer. If it's a planned stub, add a `// TODO(PR #N): Used by XyzPanel` comment.
