# Frontend / Backend Layering

When the frontend is doing more than "render some data" — synthesising rows, classifying server error codes, mirroring server enums, or running multi-stage data transforms before display — the responsibility almost always belongs on the backend.

## The Rule

**Frontend renders. Backend computes.** When you catch yourself reaching for a transform helper, a classification map, or a synthesised data structure inside a component or query layer, stop and ask whether the backend should emit the already-shaped payload.

**Why:** Business-critical logic in the frontend has a long track record of going wrong: the FE drifts from server semantics, the same logic gets re-implemented in every client (web, mobile, public API consumer), the type contract becomes a moving target, and the "compute then render" coupling makes the component much harder to test than it should be. The producer (backend) sees the canonical state; the consumer (frontend) sees a snapshot through a wire protocol that does not carry enough context. Pushing the construct to the backend keeps the frontend's job to "map this typed payload to JSX."

**How to apply:** Before merging any PR where the frontend introduces a transform/classifier/synthesiser, run the producer-side dual: "what would this look like if the backend emitted the finished shape?" If the backend version is reasonable, the FE version is the wrong layer — even if it's locally easier.

## The reviewer test

A senior reviewer reading the diff should not encounter sentences like:

- "the frontend now classifies server error kinds into connection vs model"
- "the frontend synthesises ghost rows for items the backend says are missing"
- "the frontend filters out orphans before passing to the API"
- "the frontend computes the derived status from these three flags"

If any of those describe the diff, the design is wrong. The backend should emit the classification, the ghost rows, the filtered list, or the derived status directly — and the frontend should render it.

Reviewer quote (worth keeping in mind verbatim):

> I've been seeing this happen a lot — we're baking a lot of business-critical logic into the frontend. No longer is the frontend solely responsible to "render some data". It now has to do a bunch of computation to figure out how to "swizzle" the data so that it can finally render it. Can we push down a `missing data` construct to the backend and let the frontend focus solely on rendering things?

## Symptoms in code

These are the recurring shapes. Each is a request to step back and ask whether the backend should have done this work:

### 1. Frontend mirrors a server enum into a `Set<string>`

```typescript
// ❌ BAD: 13 of 31 enum values hand-copied from a Python StrEnum,
// typed as Set<string> so the compiler can't catch drift.
const connectionErrorKinds = new Set([
  'data_connection_not_found',
  'data_connection_table_not_found',
  // ...
]);
const hasConnectionErrors = errors.some((e) => connectionErrorKinds.has(e.kind));

// ✅ GOOD: backend emits an explicit category.
type ValidationError = { kind: ValidationMessageKind; category: 'connection' | 'model' | 'verified_query' };
const hasConnectionErrors = errors.some((e) => e.category === 'connection');
```

### 2. Frontend synthesises domain objects the backend "could have" sent

```typescript
// ❌ BAD: FE invents ghost table rows for items it knows the DB doesn't have,
// then merges them with real rows, then auto-strips them from form state.
const ghostTables = mismatches
  .filter((m) => !dbTables.has(m.table))
  .map((m) => ({ name: m.table, columns: m.columns.map(ghostColumn), foreign_keys: [] }));
const allRows = [...dbTables, ...ghostTables];

// ✅ GOOD: /inspect returns rows already tagged with status.
type InspectedRow =
  | { status: 'present'; name: string; columns: Column[] }
  | { status: 'missing_in_db'; name: string; columns_from_sdm: ColumnName[] };
// FE just renders by status.
```

### 3. Frontend filters/transforms before sending to the API

```typescript
// ❌ BAD: FE strips orphans, decides what's "valid," then submits.
const realData = data
  .filter((t) => !missingTableNames.has(t.name))
  .map((t) => ({ ...t, columns: t.columns.filter((c) => !orphanedCols.has(c.name)) }));
submitMutation.mutate({ tables: realData });

// ✅ GOOD: send the user's intent; backend validates/normalises.
submitMutation.mutate({ selection: userSelection });
```

### 4. Frontend computes a "derived status" from multiple flags

```typescript
// ❌ BAD
const status =
  isLoading ? 'loading' :
  hasError && !isStale ? 'error' :
  hasError && isStale ? 'stale-error' :
  hasData ? 'ready' : 'empty';

// ✅ GOOD: server emits the status; FE picks the icon/copy.
type ConnectionStatus = 'loading' | 'error' | 'stale-error' | 'ready' | 'empty';
```

## When the frontend-side fix is legitimate

Not every transform belongs on the backend. The frontend is the right layer for:

- **Pure presentation**: truncating long strings, formatting numbers/dates for the user's locale, mapping a status code to a colour token or icon.
- **UI-state that doesn't survive a refresh**: which row is expanded, hover/focus, scroll position.
- **Composing already-finished server payloads**: rendering a list, filtering by the user's typed search query against fields the server returned.
- **Form-local validation that mirrors server-side validation**: e.g. a min/max range check for a snappier UX, where the server still has the authoritative copy.

The test: if two different clients (web + mobile + public API consumer) would need to re-implement the same logic, it belongs on the backend.

## How to push back in review

When a PR adds frontend-side classification or synthesis, surface it explicitly:

> The frontend is computing `<X>` from `<Y>` because the backend doesn't emit `<Z>`. This is server-domain logic in the wrong layer. Two options:
>
> 1. **This PR**: keep the FE transform but file a follow-up to move it server-side. Add a comment at the transform pointing to the issue.
> 2. **Move it now**: server emits `<Z>` directly, FE drops the transform.
>
> Which?

Forcing the choice explicitly avoids the path where the FE transform ships, the follow-up is forgotten, and the next reviewer inherits the same swizzle in a different feature.

## See also

- [`rules/principles.md` §1 "Producer/consumer dual"](../../../rules/principles.md#1-producerconsumer-dual) — canonical principle and the applied-lens table covering performance, API shape, error handling, and polymorphic data.
- `rules/types.md` "Wire-Format Symmetry With the Server" — when the wire shape matches, the FE doesn't need to translate. (See also [`rules/principles.md` §4](../../../rules/principles.md#4-wire-format-symmetry-as-a-design-contract).)
