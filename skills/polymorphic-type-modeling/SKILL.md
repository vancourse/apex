---
name: polymorphic-type-modeling
description: Design rules for modeling polymorphic content/events — discriminated unions with literal tags, narrow tagged types over fat optionals, classvar registry dispatcher, wire-format symmetry, single-responsibility primitives. Fires when adding a new variant/kind/event-type, a new content block, a new tool-call payload shape, or a new streaming delta. Keywords: polymorphic, variant, discriminated union, dispatcher, registry, tagged union, event type, content kind, payload.
---

# Polymorphic Type Modeling

Five rules for modeling a new polymorphic kind of thing (thread content, event, delta, progress update, tool payload, anything with variants). They supplement — do not duplicate — `python-review` and `typescript-review`.

## 1. Discriminated Unions With `Literal[...]` Tags

Every variant declares its own `type: Literal["..."]` (Python) / `type: "..."` (TS) field. The tag is part of the type, not runtime hope. Wire the union as:

- Python: `Annotated[Union[A, B, C], Field(discriminator="type")]`
- TypeScript: a discriminated union keyed on the same field with the same string literals.

The discriminator name and literal values must match byte-for-byte across both sides.

## 2. Narrow Tagged Types Over Fat Optional-Field Types

One class per variant with **required** fields for that variant. Do not introduce one umbrella type with many optionals. `FieldUpdate`, `StepProgress`, `ResourceCreated` — three small classes — beats one `ProgressDetail` with twelve `| None`s.

This is what makes downstream exhaustiveness checks meaningful and renders TS narrowing safe. The fat-optional shape pretends to be one type while behaving like three; tooling can't help you, and reviewers can't tell which fields are required when.

## 3. Dispatcher Pattern With Classvar Registry for Base-Class Deserialization

When a base class needs to deserialize into the right subclass, use:

```python
class Base(BaseModel):
    _content_kinds: ClassVar[dict[str, type["Base"]]] = {}

    @classmethod
    def register_content_kind(cls, kind: str, subclass: type["Base"]) -> None:
        cls._content_kinds[kind] = subclass

    @classmethod
    def model_validate(cls, value, *args, **kwargs):
        if isinstance(value, dict) and "type" in value:
            tag = value["type"]
            target = cls._content_kinds.get(tag)
            if target is not None and target is not cls:
                return target.model_validate(value, *args, **kwargs)
        return super().model_validate(value, *args, **kwargs)
```

Each subclass module calls `Base.register_content_kind("my_tag", MyVariant)` at import time. Look for an existing dispatcher in the codebase before inventing a new one — mirror the pattern that's already there.

## 4. Wire-Format Symmetry as a Design Contract

`model_dump` and `model_validate` must be strict inverses. Whatever shape goes out must round-trip back. The Python `Literal["x"]` tag string must match the TS discriminator literal byte-for-byte.

Treat any drift between the two sides (stripped fields, renamed keys, casing mismatch) as a bug, not a translation step. Verify with a round-trip test:

```python
original = MyVariant(type="my_kind", payload=...)
roundtrip = Base.model_validate(original.model_dump())
assert roundtrip == original
```

## 5. Single-Responsibility Primitives, Not Overloaded Kwargs

When a concern (throttling, batching, retry, rate-limiting) attaches to an operation, make it a separate class that composes with the primitive — not a kwarg on the primitive.

```python
# ❌ BAD — primitive grows kwargs that mix concerns
def emit_progress(payload, throttle=True, batch=5, retry=3): ...

# ✅ GOOD — primitive stays narrow; concerns compose
def emit_progress(payload): ...

class ProgressThrottler:
    def __init__(self, sink: Callable[[Payload], None], window_ms: int): ...
    def submit(self, payload: Payload) -> None: ...  # decides when to call sink
```

## When to Run These Rules

Fire when the user asks to add:

- A new variant / kind / event-type
- A new content block
- A new tool-call payload shape
- A new streaming delta or progress event

Before writing code, surface rules 1–3 as a short design sketch in plan mode: what are the variants, what's the discriminator literal per variant, which existing dispatcher registry to extend. When tempted to add a kwarg to an existing primitive, stop and consider whether the new concern belongs in a separate class (rule 5).
