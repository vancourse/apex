# React Hooks

Dependency arrays, cleanup, AbortController, and stale-closure patterns.

## Stale Closures & Missing Hook Dependencies — #1 Frontend Finding

**When:** A callback references state, props, or store selectors.
**Rule:** Every reactive value used inside the callback must be in the dependency array, or use a ref if you intentionally want the latest value without re-rendering.

```typescript
// ❌ BAD: formData captured at mount time
const handleSubmit = useCallback(() => {
  submitMutation.mutate({ payload: formData.payload });
}, []); // Missing formData!

// ✅ GOOD
const handleSubmit = useCallback(() => {
  submitMutation.mutate({ payload: formData.payload });
}, [formData, submitMutation]);
```

**Common offenders:** `useEffect` reading Zustand store without subscribing, `useCallback` capturing route params but omitting them, event handlers closing over parent state.

## Never Put `ref.current` in a Dependency Array

**Rule:** Mutating a ref doesn't trigger a re-render. `ref.current` in a `useEffect` dependency is effectively ignored — the effect won't re-fire when the ref changes.
**Fix:** If the value change should trigger the effect, it must be state (`useState`), not a ref.

```typescript
// ❌ BAD
useEffect(() => {
  if (hasStarted.current && responseData) openPanel();
}, [hasStarted.current, responseData]); // ref.current is stale!

// ✅ GOOD: convert to state
const [hasStarted, setHasStarted] = useState(false);
useEffect(() => {
  if (hasStarted && responseData) openPanel();
}, [hasStarted, responseData]);
```

## Include All Referenced Values in useEffect Dependencies

**Rule:** Route params, props, and any reactive value used inside the effect body must be in the deps array.

```typescript
// ❌ BAD: tenantId, agentId, threadId used but missing from deps
useEffect(() => {
  if (isPanelOpen) navigate({ to: '...', params: { tenantId, agentId, threadId } });
}, [isPanelOpen, pathname]); // missing!

// ✅ GOOD
}, [isPanelOpen, pathname, tenantId, agentId, threadId, navigate]);
```

## AbortController in Every Async Effect

**When:** A `useEffect` starts an async operation (SSE stream, fetch, file download).
**Rule:** Create an `AbortController`, pass its `signal` to the operation, and abort on cleanup.

```typescript
// ✅ GOOD
useEffect(() => {
  if (!resourceId || !sessionId) return;
  const controller = new AbortController();
  startStream({ sessionId, resourceRef: resourceId, signal: controller.signal });
  return () => controller.abort();
}, [resourceId, sessionId]);
```

## Cleanup on Component Unmount

**When:** A component establishes a persistent connection (SSE, WebSocket, polling).
**Rule:** Always return a cleanup function from `useEffect` that closes the connection.

## Guard `useEffect` Syncs Against Overwriting User Edits

**When:** A `useEffect` resets local state based on a prop (`initialSchema`).
**Rule:** Deep-compare with `useMemo` or use a stable serialized key to prevent resetting when the parent re-renders with a referentially-new but semantically-identical value.

```typescript
// ❌ BAD: resets on every render if parent passes an inline object
useEffect(() => {
  setLocalSchema(JSON.stringify(initialSchema, null, 2));
}, [initialSchema]);

// ✅ GOOD: stable key
const initialSchemaJson = useMemo(() => JSON.stringify(initialSchema), [initialSchema]);
useEffect(() => {
  setLocalSchema(initialSchemaJson);
}, [initialSchemaJson]);
```

## Async Cleanup Functions Must Handle Early Unmount

**When:** A `useEffect` calls an async function that returns a cleanup callback.
**Rule:** Use an `unmounted` flag. The `.then()` checks the flag: if already unmounted, call teardown immediately. Otherwise, store it for the cleanup function.

```typescript
// ❌ BAD: cleanup is undefined if unmount beats the promise
useEffect(() => {
  let cleanup: (() => void) | undefined;
  startWebSocket({ handlers }).then(fn => { cleanup = fn; });
  return () => { cleanup?.(); };
}, []);

// ✅ GOOD
useEffect(() => {
  let cleanup: (() => void) | undefined;
  let unmounted = false;
  startWebSocket({ handlers }).then(fn => {
    if (unmounted) { fn(); } else { cleanup = fn; }
  });
  return () => { unmounted = true; cleanup?.(); };
}, []);
```
