# Architecture & Design Patterns

Rules that apply when designing new modules, classes, or services. Gang-of-Four patterns over ad-hoc solutions.

<!-- CONFLICT: added Template Method, Factory Method, Repository patterns from lessons summary; generalized project-specific examples. -->

## Fix Root Causes — Don't Wrap Buggy Subsystems

**When:** A symptom appears (negative metric, nested-transaction error, spurious retry, silent fallback).
**Rule:** Diagnose the underlying contract violation before adding a workaround layer. Layering hides the real bug and compounds tech debt.
**Why:** If an inner subsystem is wrong, an outer layer that papers over it makes the bug permanent and invisible.
**How to apply:** If an exception "shouldn't happen here," let it propagate instead of catching. If a metric is impossible, trace where it's computed — don't clamp it.

## KISS & YAGNI

**When:** Considering abstractions, config knobs, or flexibility for hypothetical future use.
**Rule:** Complexity is a liability. Don't build generic engines when a simple `if` suffices.
**Why:** Over-engineering is the dominant review finding; it hides intent and bloats PRs.
**How to apply:** If a subsystem is buggy or unused, delete it — don't patch it. Keep PRs under 1,000 lines.

## Strategy over Optionality

**When:** 2+ algorithm paths exist (fast/slow, provider A/B, legacy/new).
**Rule:** Define an ABC and one concrete class per path. No `if config.backend == 'x'` in core logic.
**Why:** Inline branching tangles the happy path with dispatch; Strategy keeps each path focused.
**How to apply:** Pick `StrategyA() if flag else StrategyB()` at the composition root, then call methods on the abstract.

## Template Method for Fixed-Stage Pipelines

**When:** Stages always run in the same sequence (parse → schema → extract).
**Rule:** Define the skeleton in an ABC with concrete `run()`, and let subclasses override individual stages.
**Why:** Guarantees the stage order; keeps each stage independently testable and swappable.

## Factory Method for Dialect / Environment Variation

**When:** Behavior varies by environment or dialect (SQLite vs Postgres, local vs cloud).
**Rule:** Use a factory method on the base class to produce the right variant (`_dialect_insert()`).
**Why:** Avoids parallel mixin files per dialect; keeps one code path with a single extension point.

## Repository via Storage Abstraction

**When:** Any module needs to persist or read domain objects.
**Rule:** All persistence goes through a `BaseStorage` / `Repository` interface. Never bypass with raw SQL or direct DB access outside the base implementation.

## Terse Storage APIs — Rich Domain Helpers

**When:** Tempted to add a new variant method on a storage/DAO class (`update_foo_with_bar`, `update_foo_skipping_baz`).
**Rule:** Keep storage APIs in terse CRUD shape (`get`, `create`, `update`, `delete`). Put compound operations on a domain/service layer, not as storage method variants.
**Why:** "N ways to update X" on the storage class signals the domain logic leaked into persistence. Helpers belong higher up.

## Hide Compound Flows Behind a Single Method

**When:** A caller orchestrates get-or-create / upsert / cache-then-fetch.
**Rule:** Expose one method (`upsert_draft`, `ensure_session`). Callers should not care whether the cache was hit or whether the row existed.

## Promote Thrice-Repeated Logic to a Method

**When:** The same block of logic appears in three or more places operating on the same domain object.
**Rule:** Promote it to a method on that domain object. Two copies is tolerable; three is a design signal.

## Composition over Inheritance

**When:** Code reuse between related classes.
**Rule:** Assemble behavior from focused service objects. Never inherit more than 2 levels deep.
**Why:** Deep hierarchies become untouchable; composition lets each piece evolve independently.
**How to apply:** Prefer `self.slot_manager = SlotManager()` over `class X(SlotManager)`.

## Rich Domain Model (Encapsulation)

**When:** Writing logic that operates on another object's internals.
**Rule:** Put the logic on the class that owns the data. No "Utils" classes or standalone functions on domain internals.
**Why:** Anemic models scatter invariants; logic drifts away from the data it depends on.
**How to apply:** `user.process()` not `process_user(user)`. Extension functions are the anti-pattern.

## Pre-Coding Gate — Service Class Signal

**When:** 3+ functions share the same arguments (`storage`, `agent_id`, `user`).
**Rule:** Promote those to instance variables on a service class. A flat module of helpers is a smell.
**Why:** Repeated argument passing is the codebase telling you a class is missing.
**How to apply:** If you are naming a file `_xxx_utils.py`, `_xxx_helpers.py`, stop — justify or extract a service.

## Adapter for Third-Party Integrations

**When:** Wrapping a third-party client (LLM provider, cloud SDK, external API).
**Rule:** Define a project-owned interface; vendor types and exceptions never bleed into domain logic.
**Why:** Swapping vendors means swapping the adapter, not rewriting business code.
**How to apply:** `class LLMClient(Protocol): def generate(...)` — then `OpenAIAdapter`, `AnthropicAdapter`.

## Decorator for Cross-Cutting Concerns

**When:** Adding retry, rate limiting, logging, or caching to an existing service.
**Rule:** Wrap the service in a Decorator; don't modify the service itself. One decorator = one concern.
**Why:** Keeps the core service focused; concerns stack explicitly.
**How to apply:** `RetryingLLM(CachingLLM(BaseLLM()))`.

## SRP for Function Signatures — No Kwargs-Grab-Bag

**When:** A new cross-cutting concern (throttling, batching, retry, rate limiting, caching, debouncing) attaches to a primitive function.
**Rule:** Build the concern as its own class that composes with the primitive. Do **not** add a new kwarg on the primitive (`emit_progress(payload, throttle=True, batch=5, retry=3)`).
**Why:** Each new flag widens the signature, tangles dispatch, and turns a focused function into a Swiss-army knife. SRP applies to function shape, not just classes.
**How to apply:** Keep `emit_progress(*, payload, status, detail)` narrow and keyword-only. Build `_ProgressThrottler` with its own `should_commit(tool_call_id, now=None)` method and let the caller decide when to throttle. Reject signature growth in review.

## Observer for Event Streams

**When:** A component broadcasts state changes (streaming tokens, progress events) to unknown consumers.
**Rule:** Use Observer (callbacks, queues, pub/sub). No polling loops, no tight producer/consumer coupling.

## State Pattern for Lifecycle Machines

**When:** An object behaves differently based on its current status (`uploading → processing → published`).
**Rule:** Encode transitions in an explicit table. No `if status == X` chains scattered across the codebase.
**Why:** Scattered conditionals diverge over time; a single table is auditable.
**How to apply:** See `rules/types-and-models.md` — validate transitions at the method boundary.

## Facade for Subsystem Entry Points

**When:** A subsystem has internal coordination (locks, pipelines, storage).
**Rule:** One obvious method per use case. Callers never orchestrate internals.
**Why:** Scattered orchestration creates duplication and inconsistency; a Facade centralizes it.

## Split Modules at 400 Lines

**When:** A module is growing past ~400 lines.
**Rule:** Split it — one class/service per file.
**Why:** Long files hide responsibilities and make review/navigation painful.

## Name Functions by Verb, Not Calling Context

**When:** You catch yourself writing `_X_after_Y` or `_auto_update_X_when_Z`.
**Rule:** The name should answer "what does this do?" not "when is this called?"
**Why:** Context-encoded names break the moment a second caller appears.
**How to apply:** `_auto_refresh_cache_after_save` → `refresh_cache`.

## Pass Domain Objects — Read at the Edge

**When:** A service method accepts an ID and fetches the object internally.
**Rule:** Push the fetch to the caller; services operate on what they're given.
**Why:** Hidden reads inflate DB load invisibly and force tests to stub storage.
**How to apply:** Caller: `obj = await fetch(id); await service.process(obj, ...)`.

## Two-Pass Pattern to Avoid N+1

**When:** Iterating a collection to find items to modify.
**Rule:** Pass 1 collects affected IDs (scan only). Pass 2 fetches/modifies/writes one at a time.
**Why:** Interleaving reads with scans hides the read/write pattern and creates N+1.

## Separate Data Preparation from External I/O Calls

**When:** A function collects/organizes data and also makes an LLM or API call.
**Rule:** Split into two methods: pure data-prep (no I/O) and an isolated call method.
**Why:** Tests can exercise the data-prep logic without any mocks; the I/O method becomes mockable with one `patch`.

## Flatten Single-Delegation Private Methods

**When:** A private method's body is one line that calls another object's method.
**Rule:** Inline it. Extraction is only justified when the wrapper adds logic (error handling, logging, transformation) or has 3+ callers.

## Flatten Short Private Helpers With ≤ 2 Callers

**When:** A private helper has 1–2 call sites in the same file and the body is ≤ 10 lines.
**Rule:** Inline it. The indirection adds no reuse value and forces readers to jump around.
