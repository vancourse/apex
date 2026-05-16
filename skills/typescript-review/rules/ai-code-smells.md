# AI Code Smells (TypeScript)

Patterns that appear in AI-generated TypeScript/React code and almost always indicate the AI didn't understand the codebase or type system.

## Speculative Utility Functions — No Caller in This PR

**When:** A utility function, exported constant, or optional parameter has no caller in the current PR.
**Rule:** Delete it. Every function, export, and optional parameter must have a concrete, present-in-this-PR reason to exist.

**Symptoms:**
```typescript
// ❌ BAD: utility written speculatively, never called
export function isRetryableExtractionError(message: string): boolean { ... }

// ❌ BAD: parameter made optional when it is always provided
function setProcessing(isProcessing: boolean, stage?: ProcessingStage | null) { ... }
// every callsite: setProcessing(true, 'parsing') — stage never omitted

// ❌ BAD: exported constant with no consumer
export const EXTRACTION_PIPELINE_STEPS = [...];
```

**Check before submitting:**
1. Grep for every new exported symbol — confirm it has an importer in the same PR
2. For every optional parameter, verify at least one callsite omits it
3. For every error-handling utility, confirm it is called somewhere

## Three-State Nullable Fields for Values That Are Always Present

**When:** A type field is `?: T | null` for a value that is always a string at runtime.
**Rule:** Trust the type system. If the field is always provided, make it required. If never null, remove `| null`. See `rules/types.md`.

## Types Designed for Initial State, Not Domain Invariants

**When:** Every field in a type is nullable.
**Rule:** That's a type designed for the empty state, not the valid domain state. Use a discriminated union. See `rules/types.md`.

## Always-Passing Assertions

**When:** A test assertion can never actually fail (e.g., `typeof` on a declared boolean).
**Rule:** Every assertion must have a plausible failure scenario. See `rules/playwright-e2e.md`.

## Defensive Access on Typed Objects

**When:** AI generates `option?.field` or `(value as SomeType).field` on objects returned from typed internal functions.
**Rule:** If a function's return type says the value is non-null, access it directly. Fix the type upstream if needed; don't add optional chaining to paper over it.

## Dev Tooling Left In — `console.log`, `devtools`, `debugger`

**When:** Reviewing any PR with AI-assisted code.
**Rule:** AI often adds `console.log` statements for debugging during generation and forgets to remove them. Always search before submitting. See `rules/code-hygiene.md`.

## Parse External Data Defensively

**When:** Parsing SSE events, WebSocket messages, or any untrusted stream.
**Rule:** Never assume every payload is valid JSON of the expected shape. Wrap `JSON.parse` in try/catch, validate the event type, log and skip malformed events.

```typescript
// ❌ BAD: throws on malformed JSON, crashes the stream handler
eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  handleEvent(data);
};

// ✅ GOOD: defensive parse, skip bad events
eventSource.onmessage = (event) => {
  let data: StreamEvent;
  try { data = JSON.parse(event.data); }
  catch { console.warn('Malformed SSE event, skipping:', event.data); return; }
  if (!isValidEventType(data)) return;
  handleEvent(data);
};
```

## Fake Routing Pattern — A Function Named For Behavior It Doesn't Do

**When:** Reviewing a new function whose name implies a decision — `route*`, `dispatch*`, `*Filter`, `*Eligibility`, `is*Eligible`, `pick*`, `choose*` — or a config flag whose name implies a code branch.
**Rule:** Identify the single line inside the body that *actually differs* from the prior path. If you cannot point at it, the routing is fake — the function name is aspirational, not descriptive. Rename to match the actual behavior, or delete and inline.
**Why:** AI generates "router" functions that route to one destination, "filter" predicates that always return true, "eligibility" gates that are never called. These pass type checks, pass unit tests narrow to the named path, and silently regress behavior — the production system runs the legacy code while the new function sits inert.

**Smells that recur:**

```typescript
// ❌ BAD: name says "route by status" but always returns the same component
function routeByStatus(status: TaskStatus): React.FC {
  return TaskDefaultView;  // other-status branches never reachable
}

// ❌ BAD: predicate filter that always passes through
function isActionable(item: WorkItem): boolean {
  return true;  // filter does nothing
}

// ❌ BAD: "eligibility" helper exported but never imported
export function isReviewEligible(pr: PullRequest): boolean { ... }
// no importer in this PR; no importer anywhere
```

**Pre-PR check:** for every new function with one of those name patterns, ask: what's the line in the body that makes this branch different from the prior path? If the answer is "no line," the routing is fake.
