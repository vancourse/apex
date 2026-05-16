# Error Handling

Result type patterns, error codes, and exception catching.

## Error Codes as Enums — Not Magic Strings

**Rule:** Use enums for error codes. Better discoverability, refactoring support, and autocomplete.

```typescript
export enum ApiKeyErrorCode {
  ApiKeyNotFound = 'api_key_not_found',
  FailedToCreateApiKey = 'failed_to_create_api_key',
}
```

## Be Explicit About Which Error Codes Each Function Returns

**Rule:** Narrow the error code union to exactly what the function can produce. Never use the entire enum when only 2 variants are possible.

```typescript
// ❌ BAD: too generic
): Promise<Result<Data, { code: ApiKeyErrorCode; message: string }>>

// ✅ GOOD: explicit about possible errors
): Promise<Result<Data, { code: ApiKeyErrorCode.ApiKeyNotFound | ApiKeyErrorCode.FailedToDecryptApiKey; message: string }>>
```

## Result Piping — Forward Errors Early

**When:** A function calls another that returns `Result`.
**Rule:** Check and forward on failure immediately. Never nest success paths.

```typescript
const userResult = await getUser({ id });
if (!userResult.success) {
  return userResult;  // forward early
}
// continue with userResult.data
```

## Use an `asError()` Helper — Never Cast in catch Blocks

**When:** Catching an unknown error in a try/catch.
**Rule:** Use (or create) an `asError(err)` helper that normalizes an unknown to `Error`. Never `err as Error` — the caught value may be a string, object, or anything else.

```typescript
// ✅ GOOD
try {
  ...
} catch (err) {
  const error = asError(err);
  return { success: false, error: { code: 'failed_to_create', message: `${error.name}: ${error.message}` } };
}
```

## Don't Check `instanceof Error` on React Query Errors

**Rule:** React Query returns `QueryError` which always has `.message`. Never `error instanceof Error ? error.message : 'Failed'` — just use `error.message`.

## Log Error Message and Name Together

**Rule:** When logging an error, include both the message and the name/code. A message alone loses the error category; a code alone loses the context.

```typescript
logger.error('Failed to do something', {
  entityId: id,
  errorMessage: result.error.message,
  errorName: result.error.code,
});
```

## Don't Leak Internal Errors to Users

**Rule:** User-facing messages should be generic with an identifier. Internal error details (stack traces, DB errors, upstream messages) belong in logs, not the UI.

```typescript
// ❌ BAD: leaks internals
message: result.error.message

// ✅ GOOD: generic with identifier
message: `Failed to create API key "${name}"`
```

## Log at the Right Layer — Avoid Duplicates

- Managers/services: log errors internally, return user-friendly messages
- API routes calling managers: don't log again, just convert the error
- API routes calling the database directly: log at the route layer with a generic user message
- Error-logging middleware (if present) handles response-level logging automatically
