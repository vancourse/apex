# Types & Models

Pydantic, dataclasses, typing. Rules for enforcing invariants at the type level.

## No TypedDict or Raw Dict for Domain Logic

**When:** Defining request/response payloads, configuration, or intermediate pipeline structures.
**Rule:** Use Pydantic `BaseModel` or `@dataclass`. Never `TypedDict` or raw `dict[str, Any]`.
**Why:** TypedDict gives you structure without validation or methods; dicts give you nothing.

<!-- CONFLICT: tightened per reviewer feedback; previous rule gave dataclass equal standing. Pydantic is now the default; dataclass is the narrow exception. -->

## Pydantic BaseModel Is the Default — Dataclass Is the Exception

**When:** Defining any model-shaped type.
**Rule:** Default to `BaseModel`. Use `@dataclass(frozen=True)` only for pure internal results that never cross a serialization boundary — and "pure internal" is a high bar. If in doubt, use BaseModel.
**Why:** The moment a dataclass needs `model_dump` / `model_validate`, you've paid the Pydantic overhead anyway — by reimplementing it badly. Pydantic's validators and serializers are the right primitive.

```python
# ❌ BAD: hand-rolled serialization on a dataclass
@dataclass
class Config:
    name: str
    def model_dump(self) -> dict: ...
    @classmethod
    def model_validate(cls, raw: dict) -> "Config": ...

# ✅ GOOD
class Config(BaseModel):
    name: str
```

## Strict Signatures — No Any, No TypedDict-as-kwargs

**When:** Typing infrastructure code or generic helpers.
**Rule:** Use `ParamSpec` and `Generic[T]` to propagate types. Avoid `Any`. Never pass `**kwargs` between functions.
**Why:** `Any` erases invariants silently; typed payloads catch mismatches at the boundary.

## Pydantic Field Constraints, Not Docstrings

**When:** You are documenting that `limit` must be between 0 and 100,000.
**Rule:** Codify the constraint with `Field(ge=0, le=100_000)`. Don't rely on prose.
**Why:** Documentation drifts; validators run.

## ConfigDict(extra="forbid") + min_length on Request Models

**When:** Defining a request `BaseModel` for an API endpoint.
**Rule:** Set `model_config = ConfigDict(extra="forbid")`. String fields get `Field(min_length=1)` unless genuinely optional.
**Why:** Silent acceptance of unknown fields or empty strings causes subtle corruption downstream.

## PATCH Payloads: Default `None`, Not `""`

**When:** Defining an update payload where fields are optionally present.
**Rule:** Every optional field defaults to `None`. The handler skips `None` fields during update.
**Why:** Default `""` silently overwrites on every partial request.

## Reject No-Op Update Requests

**When:** An update payload has all-optional fields.
**Rule:** Add a `model_validator(mode="after")` that requires at least one non-identifier field to be set.
**Why:** Requests with only the identifier are valid but meaningless — catch them at parse time.

## Log When Silently Stripping Fields

**When:** A backward-compat validator strips deprecated fields.
**Rule:** Emit a warning log when stripping happens on API input. Silent stripping is correct for persisted migrations, wrong for live requests.

## Encode Finite State Sets as `Literal` / `Enum` — Never Raw `str`

**When:** A field takes values from a finite set (environments, dialects, sources, roles, statuses, types).
**Rule:** Type it as `Literal[...]` or `Enum` on the model. Never a free-form `str`. Prefer an explicit field (`source: Literal["manual", "imported"] = "manual"`) over hiding the key inside an `extra: dict`.
**Why:** The typing flows to the frontend, enables exhaustive handling, and the UI gets a dropdown instead of a text input.

```python
# ❌ BAD
class Model(BaseModel):
    environment: str
    extra: dict  # sometimes contains a "source" key

# ✅ GOOD
Environment = Literal["prod", "test"]
class Model(BaseModel):
    environment: Environment
    source: Literal["manual", "imported"] = "manual"
```

## Polymorphic Variants — Literal Tag + Discriminator, Not Manual Dispatch

**When:** Modeling a kind/type/event/delta family (content kinds, progress details, stream deltas, payload variants).
**Rule:** Each variant declares its own discriminator with `field(default="...", init=False)` (dataclass) or `type: Literal["..."] = "..."` (Pydantic) — callers cannot override it. Wire the union as `Annotated[A | B | C, Field(discriminator="type")]`. Validate outside a `BaseModel` with a single `TypeAdapter`. **Never** hand-roll a `{"type_a": TypeA}` dispatch dict.
**Why:** The discriminator + narrow variants give exhaustive checking, free Pydantic validation, and a wire format the TS side can mirror byte-for-byte. Manual dispatch dicts drift silently when a new variant is added.
**How to apply:**

```python
class FieldUpdate(BaseModel):
    entity_kind: str
    entity_id: str
    field: str
    type: Literal["field_update"] = "field_update"

class StepProgress(BaseModel):
    step: int
    total: int
    type: Literal["step_progress"] = "step_progress"

DetailUnion = Annotated[FieldUpdate | StepProgress, Field(discriminator="type")]

# Outside a BaseModel:
_adapter = TypeAdapter(DetailUnion)
parsed = _adapter.validate_python(raw_dict)
```

Prefer **narrow variants** over one umbrella class with a dozen `| None` fields — the consumer-side narrowing only pays off if each variant has *required* fields for its kind.

For OO dispatch where a base class deserializes into the right subclass, use a `ClassVar` registry plus a `register_*` call as the **last line** of each variant module — no metaclass tricks, no import-side-effect magic.

```python
class ThreadMessageContent(BaseModel):
    _content_kinds: ClassVar[dict[str, type["ThreadMessageContent"]]] = {}

    @classmethod
    def register_content_kind(cls, kind: str, content_class: type) -> None:
        cls._content_kinds[kind] = content_class

# tool_progress.py — last line of the file:
ThreadMessageContent.register_content_kind("tool_progress", ToolProgressContent)
```

## Collect Correlated Fields Into a Model — Not Bool + Optional Siblings

**When:** A boolean flag implies which of several sibling fields are populated.
**Rule:** Replace with a discriminated union keyed on the state. See "Polymorphic Variants" above and "Types Should Encode Invariants, Not Initial State" below.

## Validate State Transitions, Not Raw Strings

**When:** A model field is a `Literal` type (e.g., status).
**Rule:** Methods that update it must validate the transition — use a `VALID_TRANSITIONS` table and reject invalid moves.
**Why:** Accepting `str` bypasses the Literal and persists invalid data.

## Types Should Encode Invariants, Not Initial State

**When:** Every field in your type is nullable.
**Rule:** That usually means you designed for the empty state. Use a discriminated union of states.
**How to apply:** `type X = { classified: false } | { classified: true, documentType: str, ... }`.

## Don't Wrap Pydantic Primitives

**When:** Writing a helper that reconstructs a Pydantic model field-by-field.
**Rule:** Use `model.model_copy(update={...})`. Never hand-roll a copy constructor.
**Why:** Manual reconstruction breaks when new fields are added.

## Model Composition over Opaque Kwargs

**When:** A service method accepts `**kwargs` or `dict[str, object]` for structured data.
**Rule:** Define a base model for identifying fields and a derived model for extensions.

## No Type Casts in Tests — Assert Instead

**When:** You are tempted to `typing.cast(bytes, result)` in a test.
**Rule:** `assert isinstance(result, bytes)` — runtime behavior validated, type narrowed, better error message.

## Don't Disable the Type Checker

**When:** Considering `# type: ignore`.
**Rule:** Fix the design. `# type: ignore` in production code needs a justified comment; tests should avoid it unless omitting it makes the test significantly more complex.

## Don't Use list[dict] for Structured Response Fields

**When:** A response carries a list of structured objects (undo stack, history log, audit entries).
**Rule:** Define a typed Pydantic model for the element. `list[dict[str, object]]` is never the right type.

## Status Fields: Persistence vs Visibility

**When:** A `status` field governs visibility or mutability, not just persisted state.
**Rule:** Document clearly in the docstring. "persisted" and "published/visible" are orthogonal.

## Always Annotate Async pytest Fixtures That Yield Tuples

**When:** Writing an async fixture that yields a tuple.
**Rule:** Annotate the return as `AsyncGenerator[tuple[...], None]`.
**Why:** Without it, pyright can't infer element types — consumers cascade `# type: ignore`.
