# Testing — TypeScript / React tooling specifics

The generic testing methodology — scenarios-first, the 8-layer model, mocking policy per layer, CI tiering, isolation patterns, recorded fixtures, the 17 language-agnostic test design rules — lives in **`apex:test-strategy`**.

This file holds only the **TypeScript / React-specific tooling rules** that don't generalize. For Playwright-specific patterns (selectors, state-based waits, flake control), see `rules/playwright-e2e.md`.

## Vitest `vi.mock` vs MSW

**When:** Mocking external HTTP / API calls in component tests.
**Rule:** Prefer **MSW** (Mock Service Worker) for API-level mocking. Use `vi.mock()` for modules that aren't HTTP boundaries (utilities, helpers, narrow internal modules).
**Why:** MSW intercepts at the network boundary — your component test exercises the real `fetch` / TanStack Query code path with realistic responses. `vi.mock` of `useQuery` replaces the hook entirely; the test no longer verifies query keys, retry behavior, cache invalidation, or error handling.

```typescript
// ✅ GOOD: MSW handler intercepts at the network layer
server.use(
  http.get('/api/transactions', () => HttpResponse.json({ items: [/* ... */] })),
);
render(<TransactionsPage />, { wrapper: QueryClientWrapper });
expect(await screen.findByText('First Txn')).toBeInTheDocument();

// ❌ BAD: vi.mock of the query hook — bypasses cache, query keys, retry
vi.mock('@/hooks/useTransactions', () => ({
  useTransactions: () => ({ data: [/* ... */], isLoading: false }),
}));
```

Reserve `vi.mock` for true module-level stubbing that MSW can't reach (a synchronous utility, a third-party SDK initialized at module load).

## `@testing-library/react` + `@testing-library/user-event`

**Rule:** Use `userEvent.setup()` and `await user.click(...)` over `fireEvent.click(...)`. Use `screen.getByRole('button', { name: /save/i })` over `screen.getByTestId('save-button')`.
**Why:** `userEvent` simulates real user behavior (keyboard / focus / pointer events) vs `fireEvent` which dispatches a single synthetic event. `getByRole` mirrors how assistive tech queries the DOM — your test passes when accessibility passes.

```typescript
const user = userEvent.setup();
render(<SaveForm onSave={onSave} />);
await user.click(screen.getByRole('button', { name: /save/i }));
expect(onSave).toHaveBeenCalledWith({ name: 'foo' });
```

`getByTestId` is the last resort, for non-semantic elements where no role / label / text / placeholder applies.

## TanStack Query — Fresh QueryClient Per Test

**When:** Component tests render a component using `useQuery` / `useMutation`.
**Rule:** Wrap the test render in a fresh `QueryClient` per test. Don't share across tests; query cache pollution causes order-dependent failures.

```typescript
function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}
```

`retry: false` and `gcTime: 0` prevent inter-test bleed and slow async waits.

## Zod-Validated Test Payloads

**When:** Testing API request/response shapes.
**Rule:** Build payloads via `MyRequestSchema.parse({/* ... */})`. Parse responses via `MyResponseSchema.parse(json)`. Assert on validated objects, not raw JSON.
**Why:** Zod validates at construction; a typo becomes a test-author error, not a hidden mismatch. TS type checker catches schema refactors. (Methodology rationale: `apex:test-strategy` Rule 9.)

```typescript
// ✅ GOOD: validated payload + parsed response
const payload = CreateTxnRequestSchema.parse({ amount: '100.00', accountId: uuidv4() });
const response = await fetch('/api/txn', { method: 'POST', body: JSON.stringify(payload) });
const parsed = CreateTxnResponseSchema.parse(await response.json());
expect(parsed.status).toBe('pending');

// ❌ BAD: raw JSON
const response = await fetch('/api/txn', { method: 'POST', body: JSON.stringify({ amount: 100, accountId: '...' }) });
expect((await response.json()).status).toBe('pending');
```

## Type-Cast Avoidance in Tests

**When:** Tempted to write `result as Buffer` or `(value as any).field` in a test.
**Rule:** Use a runtime type-narrowing pattern instead:

```typescript
// ✅ GOOD: narrow with a check
if (!(result instanceof Buffer)) throw new Error('expected Buffer');
expect(result.length).toBe(1024);

// ❌ BAD: cast lies if the runtime type doesn't match
const buf = result as Buffer;
expect(buf.length).toBe(1024);  // crashes obscurely if result isn't a Buffer
```

Same principle as `apex:test-strategy` Rule 10, TS form.

## Component Test Shape

For a component with non-trivial behavior:

```typescript
describe('SaveForm', () => {
  it('calls onSave with form values when user submits', async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();

    renderWithClient(<SaveForm onSave={onSave} />);

    await user.type(screen.getByLabelText(/name/i), 'foo');
    await user.click(screen.getByRole('button', { name: /save/i }));

    expect(onSave).toHaveBeenCalledWith({ name: 'foo' });
  });
});
```

Asserts on user-visible behavior (the callback fires with the right shape). Doesn't assert on internal state, internal classes, or `render` output structure.
