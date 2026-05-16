---
name: protocol-first-workflow
description: Python Protocol-first TDD workflow — define type contracts before implementation, generate stubs alongside production code, enforce mock-count limits in tests. Fires when starting a new Python component, refactoring collaborators, or writing tests with too many mocks. Keywords: python, protocol, abc, tdd, stubs, mocks, dependency injection, interface segregation.
---

# Protocol-First Code Creation Workflow

A structured workflow for producing Python code with AI assistants. The goal
is to front-load design decisions so review feedback is about nuance, not
architecture.

**Core insight:** have the assistant write code using only interfaces. Force
the idea in your head to be expressed solely in terms of the generics, then
turn that into your implementation plan.

---

## Phase 1: Protocols & Boundaries

Before writing any implementation, produce **only** the protocols/ABCs.

### Prompt template

> I need to build [component]. Before any implementation:
>
> 1. Define Protocol classes for every collaborator this component depends on.
> 2. Define the public interface (Protocol or ABC) for the component itself.
> 3. Show constructor signatures with all collaborators as injected parameters.
> 4. No implementations yet — just the type contracts.

### Self-review checklist

- [ ] Can I test each class by supplying a fake for each collaborator?
- [ ] Does each Protocol have **only** the methods its consumer calls?
      (Interface Segregation)
- [ ] Are all collaborators injected, not constructed internally?
- [ ] If a collaborator must be constructed internally (e.g., it needs
      runtime data), is there a factory parameter or `_get_*` method that
      tests can override?

**If the answer to any of these is "no", fix the design before proceeding.**

---

## Phase 2: Implementation + Stubs Together

When generating the implementation, always generate test stubs in the same
step.

### Prompt template

> Now implement [component] and for each Protocol defined in Phase 1, also
> write a minimal stub/fake implementation suitable for testing. The stubs
> should:
>
> - Return realistic domain objects (not MagicMock)
> - Be stateless no-ops unless the test needs to observe a side effect
> - Not contain assertions (assertions belong in the test, not the stub)

### Why stubs alongside implementations

If a stub is hard to write, the Protocol is too wide or the boundary is
unclear. That friction is the signal — fix the interface before continuing.

---

## Phase 3: Tests

### The mock-count rule

Before reading any test logic, count `MagicMock` / `patch()` calls:

| Count | Action                                                                                                                                             |
| ----- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0     | Ideal. Move on.                                                                                                                                    |
| 1-2   | Acceptable if they are at external API boundaries (HTTP clients, LLM, object store).                                                               |
| 3+    | Stop. Ask: "Which of these represent collaborators that should be injected instead of constructed internally? Refactor the production code first." |

### What gets mocked vs. what gets stubbed

| Boundary type              | Technique                  | Example                                             |
| -------------------------- | -------------------------- | --------------------------------------------------- |
| External API (network I/O) | `patch()` / `MagicMock`    | HTTP client, LLM API, object store SDK              |
| Internal service           | Stub class (Protocol impl) | `_StubSomeService`                                  |
| Infrastructure             | Real local impl            | `SQLiteStorage(":memory:")`, `LocalFileManager(tmp_path)` |
| Observability / metrics    | No-op stub class           | `_StubServerContext`                                |

### Prompt template for test generation

> Write tests for [component]. Rules:
>
> - Use the stub/fake classes from Phase 2 for internal collaborators.
> - Use real local implementations for infrastructure (in-memory DB,
>   tmp-path filesystem).
> - Only `patch()` external API boundaries (network calls).
> - Zero `MagicMock` for internal types — use real domain objects.
> - Assert on domain outputs, emitted events, or persisted state — not on
>   mock call counts.

---

## Phase 4: Pre-Review Self-Check

Before asking for review, verify:

1. **Mock count:** 0–2 patches per test, all at external boundaries.
2. **No `MagicMock` for internal types:** domain objects and context objects
   should be real instances or typed stubs.
3. **Protocols live in `TYPE_CHECKING`:** they don't add runtime overhead.
   Production code depends on them only for type annotations.
4. **Stubs use real domain objects:** `DomainObject(id="obj-1", name="Example")`,
   not `MagicMock(id="obj-1")`.
5. **No assertions inside stubs:** stubs return canned data. Tests make
   assertions.

---

## Quick Reference: Java to Python Mental Model

| Java concept          | Python equivalent                                 |
| --------------------- | ------------------------------------------------- |
| `interface Foo`       | `class Foo(Protocol):` (in `TYPE_CHECKING`)       |
| `abstract class Foo`  | `class Foo(ABC):` with `@abstractmethod`          |
| Constructor injection | `__init__` parameters typed to Protocols          |
| `@Mock` / Mockito     | Stub classes implementing the Protocol            |
| Factory pattern       | `Callable[..., T]` parameter or `_build_*` method |
| `@VisibleForTesting`  | Optional `None`-defaulted param in `__init__`     |

---

## Anti-Patterns to Catch Early

1. **Inline construction:** `svc = SomeService(self._storage, self._id)`
   inside a method. Fix: extract to `_get_svc()` with optional injection, or
   accept a Protocol in `__init__`.

2. **Patching the class under test:**
   `patch("module.MyClass._internal_method")`. Fix: the internal method is
   hiding a collaborator. Extract it behind a Protocol.

3. **MagicMock with manual attribute wiring:**
   `mock = MagicMock(); mock.user_id = "u-1"; mock.start_span.return_value.__enter__ = ...`.
   Fix: use a real instance (`User(...)`) or a 5-line stub class.

4. **`ExitStack` with 3+ patches:** if your test fixture needs a stack of
   patches to set up the world, the production code has too many hidden
   dependencies. Step back to Phase 1.
