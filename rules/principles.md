# Cross-Cutting Design Principles

Canonical statements of design principles that appear across multiple skills. Skills apply these to specific contexts (planning, API shape, frontend/backend layering, polymorphic types) — this file holds the principle itself, stated once.

## 1. Producer/Consumer Dual

**Principle.** Before adopting any fix that lives on the consumer side (caller, frontend, downstream), write down what the producer-side fix would look like. Even if you ultimately stay with the consumer-side fix, you've considered both.

**Why.** Bias reliably tilts toward consumer-side workarounds because they're locally easier — the producer is "someone else's code," the consumer is what you're editing. But the producer usually has the canonical state and can emit the right shape at lower total cost.

**How it appears in practice.**

| Context | Consumer-side fix | Producer-side fix |
|---|---|---|
| Performance (N-record loops) | Add a flag, lazy-load, hydration map, isExpanded gate | Single batch query that returns the same data |
| API shape | Frontend transforms / classifies / synthesises a payload | Backend emits the already-shaped payload |
| Error handling | Caller branches on string-match of error message | Producer emits a stable error code + structured fields |
| Polymorphic data | Caller does `if obj.has_x: ... else: ...` | Producer emits a tagged variant with required fields |

**Anti-pattern phrases that signal a consumer-side workaround:**

- "Add a lazy query / fetch hook for X"
- "Gate this on isExpanded / isVisible / on demand"
- "Hydration map / effective columns / loaded-state tracking"
- "Disable the action until [data] hydrates"
- "Skip the inner loop when flag is false"
- "Frontend classifies the server error code"
- "Frontend synthesises ghost rows for missing items"

Each is sometimes correct. All are *symptoms of consumer-side workarounds for producer-side gaps* — re-check the producer-side dual before committing.

## 2. Beware the First Plausible Affordance

**Principle.** When an existing flag, option, or path looks "broken but fixable," do not let it eat the design decision. Add it to the alternatives list and run the same adversarial pass against it as any other option.

**Why.** The cheap "just fix this flag" framing is how the wrong design ships. An existing affordance that doesn't quite work creates an unwarranted gravitational pull — the cost of using it feels lower because it's already there, even when building the right path is faster and cleaner.

**How to apply.** When you catch yourself proposing "extend X to support Y," stop and ask: would I propose this design if X didn't exist? If no, the existing affordance is the reason, not the design merit. Treat it as one candidate among 2-3 alternatives, not the default.

## 3. Pure-Addition Designs Are a Smell

**Principle.** If a proposed design only adds code (no deletions, no consolidation), explain why no existing path can be extended or reused.

**Why.** Most non-trivial features have neighbours in the codebase. A design that doesn't touch any of them is either (a) genuinely the right shape and the neighbours are correctly distinct, or (b) a fresh implementation of something that already exists at a slightly different angle. Case (b) is far more common than case (a).

**How to apply.** Before finalizing a design, grep for sibling concepts: per-dialect / per-connector / per-engine abstractions, similarly-named modules, similar return types. If a sibling exists, the new code belongs near it. If you cannot find a sibling, justify the absence — that's the case (a) test.

## 4. Wire-Format Symmetry as a Design Contract

**Principle.** When the same data crosses a wire boundary (frontend ↔ backend, service ↔ service, persistence ↔ memory), the serializer and deserializer must be strict inverses. Whatever shape goes out must round-trip back.

**Why.** Asymmetric wire formats are a slow-burn class of bug: a field gets stripped on the way out, gets defaulted on the way in, and the system "works" but loses information at every hop. Discriminator literals must match byte-for-byte across language boundaries.

**How to apply.** For any new payload that crosses a boundary:

- The Python `Literal["x"]` tag must match the TypeScript discriminator literal exactly.
- `model_dump()` followed by `model_validate()` must equal the original.
- Casing, key names, optional/required must match on both sides.

Verify with a round-trip test. Treat drift between the two sides as a bug, not a translation step.

## 5. Single-Responsibility Primitives, Not Overloaded Kwargs

**Principle.** When a concern (throttling, batching, retry, rate-limiting) attaches to an operation, make it a separate class that composes with the primitive — not a kwarg on the primitive.

**Why.** Kwargs on a primitive grow without bound: every new concern adds a parameter, every parameter interacts with the others, and the primitive's contract becomes "do the thing, plus N policies." Composition keeps the primitive narrow and lets policies be tested, swapped, and reasoned about independently.

**How to apply.**

```python
# BAD — primitive grows kwargs that mix concerns
def emit_progress(payload, throttle=True, batch=5, retry=3): ...

# GOOD — primitive stays narrow; concerns compose
def emit_progress(payload): ...

class ProgressThrottler:
    def __init__(self, sink: Callable[[Payload], None], window_ms: int): ...
    def submit(self, payload: Payload) -> None: ...  # decides when to call sink
```

## Where these principles are applied

| Principle | Applied in |
|---|---|
| Producer/consumer dual | `apex-flow` §1a (planning), `api-surface-review` Pass 5 (API shape), `typescript-review` frontend-backend-layering (FE/BE split) |
| First plausible affordance | `apex-flow` §1a (planning) |
| Pure-addition smell | `apex-flow` §1b (adversarial design checklist) |
| Wire-format symmetry | `polymorphic-type-modeling` rule 4 |
| SR primitives | `polymorphic-type-modeling` rule 5 |

Skills should reference this file by section rather than restating the principle. Apply the principle in the skill's own context; let the canonical statement live here.
