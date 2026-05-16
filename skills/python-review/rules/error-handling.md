# Error Handling

Rules for exceptions, error propagation, and fail-fast behavior.

## Raise Specific, Meaningful Exceptions

**When:** Signaling a domain error.
**Rule:** Define specific exception subclasses (`SDMNotFoundError(PlatformHTTPError)`). Never raise bare `Exception` for a domain error.
**Why:** Specific exceptions let callers handle conditions selectively; bare `Exception` forces catch-all.

## Fail Fast — Never Mask Errors

**When:** Tempted to catch an exception and return `None` to keep running.
**Rule:** Let errors propagate. "If it breaks, let it crash so we fix it."
**Exception:** Only mask for non-critical UI/display helpers where a default is genuinely acceptable — and document it.

## No Broad `except` — Catch Exactly What You Understand

**Rule:** `except Exception` and `except (SpecificError, Exception)` are banned. Catch the single named exception you know how to handle; let everything else propagate.
**Why:** Broad catches suppress real bugs. A parse error and an unexpected programming error should not be handled identically.

```python
# ❌ BAD: the bare Exception masks anything unexpected
try:
    data = json.loads(payload)
except (json.JSONDecodeError, Exception):
    data = {}

# ✅ GOOD
try:
    data = json.loads(payload)
except json.JSONDecodeError:
    data = {}
```

## Don't Fall Back to Wrong Data

**When:** Tempted to catch and return a default (silent `None`, default config, previous model).
**Rule:** If the fallback causes the caller to operate on incorrect data (wrong model, stale config, missing artifact), raise. Enumerate explicitly what each fallback means and reject the ones that silently corrupt downstream behavior.

## Conditional Copy-Back = Silent Data Loss

**When:** A multi-step pipeline writes state to a temp location and copies it back.
**Rule:** The copy-back must be unconditional. If the source file is missing, raise — never silently skip.

```python
# ❌ BAD: silent skip when state file is missing
state_file = next((f for f in files if f.file_ref == "state.json"), None)
if state_file:
    ...

# ✅ GOOD: fail explicitly
if state_file is None:
    raise SDMAgentFallbackError("Agent did not produce state.json")
```

## Return What You Persisted — Not What You Received

**When:** A function normalizes input, persists it, and returns a summary.
**Rule:** Return the persisted (normalized) version, not the raw input.
**Why:** A gap between what the caller sees and what the state holds causes subtle downstream bugs.

## Validate File Artifacts Before Processing

**When:** Reading file artifacts (PDFs, JSON state) before passing to a pipeline.
**Rule:** Check for empty/unreadable files. Wrap `model_validate_json` in a try/except and raise a structured error on failure.

## Graceful Parse Failure — Don't Silently Return Empty String

**When:** A parser fails to read a document.
**Rule:** Raise a structured error. Only return `""` as a fallback when the caller explicitly opts in with a `strict=False` argument.
**Why:** A silent `""` pushes empty data into downstream LLM prompts and validators with no indication something went wrong.

## Close File Handles — Use Context Managers

**When:** Opening files for parsing (e.g., `PdfReader`).
**Rule:** Always use a context manager. Without it, repeated calls accumulate open file handles under load.

## Never Use `assert` as a Production Guard

**When:** Writing a runtime invariant check in non-test code.
**Rule:** `assert` is stripped with `-O`. Use `if condition: raise RuntimeError(...)` for invariants that must hold in production.

```python
# ❌ BAD: stripped in production
assert upsert_result.record.id is not None

# ✅ GOOD: always enforced
if upsert_result.record.id is None:
    raise RuntimeError("upsert returned no ID — cannot proceed")
```

**Reserve `assert` for test files only.**

## Transactional Integrity — Roll Back on Failure

**When:** A multi-step operation (create → import → save) can partially succeed.
**Rule:** Wrap in try/except; roll back earlier steps on failure. See `rules/types-and-models.md` for the ACID pattern.
