# Playwright E2E Tests

State-based waits, test isolation, selectors, and test data hygiene.

## State-Based Waits — Replace `waitForTimeout` Everywhere

**Rule:** Fixed waits (`waitForTimeout(1000)`) are the #1 source of Playwright flakiness. Always wait for an observable state instead.

```typescript
// ❌ BAD: arbitrary fixed wait
await page.waitForTimeout(2000);

// ✅ GOOD: wait for the expected state
await expect(page.getByText('Undo successful')).toBeVisible({ timeout: 10000 });
```

## Full Test Isolation — Fresh Context Per Test

**Rule:** Each test gets its own browser context with auth state. Never share a single page/context across tests in a `describe` block.

```typescript
// ❌ BAD: shared page — state leaks between tests
test.describe('Feature', () => {
  let page: Page;
  test.beforeAll(async ({ browser }) => { page = await browser.newPage(); });
});

// ✅ GOOD: fresh context per test
test('creates and verifies', async ({ browser }) => {
  const context = await browser.newContext({ storageState: AUTH_STATE_PATH });
  const page = await context.newPage();
  // ...
  await context.close();
});
```

## No Hardcoded Test Values — Use Env Vars

**Rule:** Never hardcode environment-specific values (URLs, tenant IDs, agent IDs) in test files or configs.

```typescript
// ❌ BAD
const AGENT_ID = '075b0207-32c6-4c9e-8340-5755f6a12fc4';

// ✅ GOOD
const AGENT_ID = process.env.E2E_AGENT_ID ?? '';
```

## File Paths in Configs — Relative to the Config File

**When:** Setting `testDir` or other path in Playwright config.
**Rule:** Use paths relative to the config file location, not the repo root or CWD.

```typescript
testDir: '../../server/tests/integration/e2e',  // relative to config
```

**Verify:** After changing a config path, run `npx playwright test --list` to confirm resolution.

## Always-Passing Assertions Are Worse Than None

**Rule:** Every assertion must have a plausible failure scenario. If it can't fail, it's not testing anything. Mark untestable scenarios as `test.fixme()` instead.

```typescript
// ❌ BAD: always true
expect(typeof isDraft).toBe('boolean');

// ✅ GOOD: asserts the actual state
expect(isDraft).toBe(false);
await expect(page.getByText('Retry')).toBeVisible();
```

## Soft-Pass Tests Must Be Visible in Results

**When:** Using a "log warning + return 0 on failure" strategy.
**Rule:** Track soft-pass count. Report it prominently in the summary. Consider a `--strict` flag that converts soft-passes to hard failures in CI.

## Clean Up Published Test Data

**When:** A test publishes schemas, creates threads, or uploads files.
**Rule:** Clean up in `afterEach` or use unique names to avoid collisions across runs.

```typescript
test.afterEach(async ({ request }) => {
  await request.delete(`/api/schemas/${testSchemaId}`);
});
// OR: unique names
const schemaName = `Test Schema ${Date.now()}`;
```

## Shell-Based E2E (agent-browser) — Session-Scoped Temp Files

**Rule:** Use unique `--session` IDs per chain to prevent `/tmp/snapshot` file collisions. Kill existing daemons before starting a new chain. Use `/tmp/snapshot_${SESSION_ID}.txt`.
