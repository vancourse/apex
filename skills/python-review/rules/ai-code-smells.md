# AI Code Smells (Python)

Patterns that appear in AI-generated code and almost always indicate a misunderstanding of the type hierarchy or domain model.

## `getattr` / `hasattr` / `isinstance` on Domain Objects — Always Wrong

**When:** AI writes `getattr(obj, "attr", default)`, `hasattr(obj, "attr")`, or `isinstance(obj, SomeType)` on an object whose type you control.
**Rule:** Trust the type system. Access the attribute directly.
**Why:** These patterns destroy type safety, hide real bugs behind silent fallbacks, and make code unreadable. The AI wrote them because it doesn't know the actual type — not because the attribute might be absent.

```python
# ❌ BAD: AI-style defensive access
use_legacy = getattr(settings, "use_legacy_extractor", False)
if hasattr(settings, "extra") and isinstance(settings.extra, dict):
    use_legacy = use_legacy or settings.extra.get("use_legacy_extractor", False)

# ✅ GOOD: trust the type
use_legacy = settings.use_legacy_extractor
```

**When these ARE legitimate:**
- `isinstance` in type-narrowing on a `Union` return type (`Result[Ok, Err]`, `ResultFullResult | other`)
- `getattr` for genuine metaprogramming (serialization, ORM internals, plugin loaders)
- `hasattr` for duck-typing at a system boundary (external library object)

**Red flags:**
- Accessing an attribute on an object whose type you control
- Guarding against `None` when the type isn't `Optional` — fix the type
- `callable()` to check if something is a method
- `isinstance` on an object just returned from a typed function

## Read SDK Types Before Writing Defensive Access

**When:** Working with a third-party SDK type (Reducto, Pydantic clients, cloud SDKs).
**Rule:** Open the SDK source (`inspect.getfile(TheType)` or `.venv/lib/`) and read the actual field definition before using `getattr`, `Optional`, or null-guards.
**Why:** The AI defaults to defensive access because it hasn't read the SDK source. If the field is `field: str` (non-optional), access it directly.

```python
# ❌ BAD: AI assumes job_id might not exist
job_id = getattr(parse_response, "job_id", None)
return str(job_id) if job_id else None

# ✅ GOOD: SDK says `job_id: str` — access directly
return parse_response.job_id
```

## Speculative Utility Functions With No Caller

**When:** A new utility function, exported constant, or optional parameter has no caller in the current PR.
**Rule:** Delete it. If a parameter is never omitted, make it required. If a field is never `null` in practice, don't type it as nullable.
**Check:** Grep for every new exported symbol — confirm it has an importer in the same PR. For every optional parameter, confirm at least one callsite omits it.

## Bound Parsing Limits — Don't Override to "Unlimited"

**When:** Passing `max_pages=999` or `max_chars=500000` to override parser defaults.
**Rule:** Use bounded configurable defaults via env vars. See `rules/security.md`.

## `str(None)` Produces Literal `"None"` — Guard Dict-to-String Conversions

**When:** Converting a dict value to a string with `str(value)`.
**Rule:** Guard against `None` before calling `str()`. `str(None)` produces the literal string `"None"`, corrupting downstream consumers.

```python
# ❌ BAD: if value is None → system_prompt = "None" (literal!)
system_prompt = str(document_extraction["system_prompt"])

# ✅ GOOD
system_prompt = document_extraction.get("system_prompt") or ""
```

## Don't Pass Internal Keys as LLM Labels — Use Human-Readable Display Values

**When:** Asking an LLM to classify or choose among a set of options.
**Rule:** Pass human-readable display labels to the LLM, not internal storage keys like `{uuid}::{name}`. Maintain a `display_label → internal_key` reverse mapping to resolve the LLM's choice.
**Why:** LLMs cannot reliably reproduce compound/opaque keys (UUIDs, `::` separators) verbatim, causing lookup failures.

```python
# ❌ BAD: compound internal keys as LLM labels
lookup = {f"{dataset_id}::{schema.name}".lower(): (dataset, schema) for ...}
label = await llm_classify(available_labels=sorted(lookup.keys()))
entry = lookup.get(label.lower())  # fails — LLM can't echo UUIDs

# ✅ GOOD: extract display labels, keep reverse map
display_to_key = {schema.name.lower(): key for key, (_, schema) in lookup.items()}
label = await llm_classify(available_labels=sorted(display_to_key.keys()))
entry = lookup.get(display_to_key.get(label.lower()))
```

## Don't Prompt the LLM to Enforce What Code Can Enforce

**When:** Tempted to instruct the LLM "don't return X" or to post-process its output to rename/reshape things.
**Rule:** If a constraint is deterministic (valid names, required fields, allowed enums, payload shape), enforce it in code — generate the payload, validate with a parser, or coerce the response. Don't spend tokens telling the LLM what not to do.
**Why:** Every negative instruction is a test you'll eventually fail. Burns tokens, lowers accuracy, invites brittle retry logic.

```python
# ❌ BAD: ask the LLM to not produce spaces in names, then raise if it does
prompt = "...use snake_case, never include spaces..."
if " " in response.name:
    raise InvalidName(response.name)

# ✅ GOOD: coerce deterministically
response.name = response.name.replace(" ", "_")
```

## LLM Output Must Round-Trip Through a Validator With Feedback

**When:** Calling an LLM whose output must satisfy a schema or parser.
**Rule:** prompt → parse → on failure, feed the parse error back into the prompt and retry → after N failures, raise a structured error. Never `return {}` / `return None` on parse failure.
**Why:** Silent empty returns deceive callers into thinking work succeeded. The retry with the parse error as context is what makes schema-bound LLM calls reliable.

## All Code Paths Must Emit the Same Event Shape

**When:** An event (WebSocket, SSE, API response) can be emitted from multiple code paths (cache-hit vs. full pipeline).
**Rule:** Every path must populate the same fields. Missing fields cause silent UI failures — blank sections, null displays.
**How to apply:** Grep for every location that emits the event type. Verify all locations populate the same fields. Consider a TypedDict or dataclass to enforce shape at the type level.
